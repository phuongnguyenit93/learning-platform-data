# Credential verification — Kiểm tra bằng chứng xác thực

## 1. Credential verification giải quyết việc gì?

**Credential verification** là việc hệ thống kiểm tra bằng chứng được trình lên để quyết định một yêu cầu có chứng minh được quyền kiểm soát phương tiện xác thực gắn với một chủ thể hay không. Trong bài này, thuật ngữ được dùng theo nghĩa thực hành ở tầng xác thực: kiểm tra mật khẩu, mã dùng một lần, phản hồi mật mã hoặc token theo cơ chế tương ứng.

NIST mô tả xác thực thông qua việc chứng minh quyền kiểm soát một hoặc nhiều authenticator đã gắn với tài khoản. Kết quả này không tự chứng minh tên pháp lý của người đang dùng tài khoản, cũng không tự cấp mọi quyền truy cập. [NIST SP 800-63B-4 — Introduction](https://pages.nist.gov/800-63-4/sp800-63b/introduction/).

Ví dụ, An nhập username và mật khẩu vào cổng nhân sự. Username giúp tìm đúng tài khoản; hệ thống còn phải kiểm tra mật khẩu theo dữ liệu xác minh đã lưu. Nếu tài khoản yêu cầu MFA, mật khẩu khớp mới hoàn tất một bước. Sau khi xác thực đầy đủ, việc An được xem hồ sơ của ai vẫn thuộc authorization.

Một validator trả về `true` chỉ có ý nghĩa trong phạm vi kiểm tra của nó. Cần biết nó xác nhận điều gì, cho tài khoản nào, trong giao dịch nào và còn thiếu điều kiện gì trước khi tạo phiên.

## 2. Phân biệt định danh, bí mật và bằng chứng trình lên

| Thành phần | Vai trò | Ví dụ minh họa |
|---|---|---|
| Định danh được khai | Chỉ ra tài khoản hoặc namespace cần xét | Username, email đăng nhập, subject tại IdP |
| Authenticator | Phương tiện được chủ thể kiểm soát | Ứng dụng TOTP, khóa bảo mật, phương tiện giữ passkey |
| Bí mật hoặc khóa | Cơ sở để tạo hay kiểm tra bằng chứng | Mật khẩu, TOTP seed, khóa riêng |
| Bằng chứng trình lên | Dữ liệu được verifier kiểm tra trong lần sử dụng | Mật khẩu nhập vào, mã OTP, phản hồi ký số |
| Dữ liệu xác minh phía máy chủ | Dữ liệu tin cậy phục vụ kiểm tra | Password hash, public key đã đăng ký, trạng thái giao dịch |

Bảng là cách phân tích thực hành, không thay định nghĩa credential của từng tiêu chuẩn. Một email đúng định dạng không phải bằng chứng người gửi kiểm soát tài khoản. Một credential ID cũng chỉ giúp tìm bản ghi, không thay chữ ký hoặc proof cần kiểm tra.

Không phải cơ chế nào cũng gửi bí mật dài hạn lên máy chủ. Với xác thực khóa công khai, máy chủ kiểm tra phản hồi bằng public key; không cần người dùng gửi private key. Với mật khẩu được kiểm tra tập trung, verifier nhận giá trị qua kênh được bảo vệ và kiểm tra theo cơ chế dành cho mật khẩu.

## 3. Luồng kiểm tra cần giữ các ràng buộc

Một luồng minh họa có thể được mô tả như sau:

```text
Nhận yêu cầu qua kênh được bảo vệ
  → Kiểm tra kiểu dữ liệu, kích thước và ngữ cảnh yêu cầu
  → Áp dụng kiểm soát số lần thử
  → Xác định tài khoản, namespace và credential cần xét
  → Kiểm tra proof bằng validator đúng loại
  → Kiểm tra trạng thái tài khoản, credential và giao dịch
  → Hoàn tất bước tiếp theo hoặc từ chối
  → Chỉ tạo phiên phù hợp khi đủ yêu cầu xác thực
```

Đây là quan hệ logic, không phải thứ tự bắt buộc cho mọi framework. Một số kiểm soát cần thực hiện trước thao tác tốn tài nguyên; một số trạng thái phải được kiểm tra lại khi commit để tránh thay đổi đồng thời.

Ví dụ, xác minh OTP đúng nhưng gắn kết quả vào tài khoản do client tùy ý gửi là sai ranh giới. Tương tự, kiểm tra chữ ký đúng mà dùng nhầm public key của tài khoản khác cũng không tạo ra kết quả xác thực hợp lệ.

Các bước nhập liệu không được tự quyết định trạng thái bảo mật. Những field như `verified=true`, `mfaComplete=true` hoặc `accountEnabled=true` trong request không phải nguồn chứng minh các điều kiện đó.

## 4. Kiểm tra mật khẩu bằng password verifier

### 4.1. Không giải mã hash và không so hai lần encode mới

Mật khẩu dùng để xác thực nên được bảo vệ bằng password hashing phù hợp với salt và cấu hình chi phí. Một phép băm nhanh đơn lẻ không thay thế password hashing chống đoán ngoại tuyến. Hash không được thiết kế để giải mã lấy lại mật khẩu. [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).

Trong thư viện có salt ngẫu nhiên, cùng một mật khẩu có thể tạo ra các chuỗi hash khác nhau qua những lần encode riêng. Vì vậy, không làm:

```java
// Sai: encode mới có thể dùng salt mới.
boolean valid = passwordEncoder.encode(rawPassword).equals(storedHash);
```

Thay vào đó, dùng API kiểm tra của thư viện. Với Spring Security, `PasswordEncoder.matches(rawPassword, storedHash)` kiểm tra giá trị nhập theo bản mã hóa đã lưu. Không cần tự tách salt hoặc viết hàm so sánh hash riêng. [Spring Security — Password Storage](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html).

### 4.2. Nhất quán giữa lúc đặt và lúc kiểm tra

Không tự ý cắt ngắn mật khẩu, chuyển về chữ thường hoặc bỏ khoảng trắng chỉ để “dễ đăng nhập”. Những biến đổi đó có thể làm nhiều mật khẩu khác nhau trở thành cùng một giá trị. Nếu có xử lý Unicode theo chính sách, phải được thiết kế và áp dụng nhất quán; NIST đề cập NFC trước bước hashing khi chấp nhận Unicode. [NIST SP 800-63B-4 — Password Verifiers](https://pages.nist.gov/800-63-4/sp800-63b/authenticators/#passwordver).

Cần phân biệt chuẩn hóa định danh với xử lý bí mật. Một hệ thống có thể quy định username không phân biệt hoa thường, nhưng điều đó không cho phép gọi `toLowerCase()` trên mật khẩu.

Trong kiểm thử, dùng các giá trị thử chỉ khác phần cuối, chữ hoa hoặc khoảng trắng. Kết quả cần đúng với contract đã công bố. Cũng cần kiểm tra giới hạn đầu vào trước khi gọi hàm password hashing tốn tài nguyên, thay vì để một request cực lớn tiêu thụ tài nguyên ngoài thiết kế.

### 4.3. Nâng cấp hash không làm yếu bước xác minh

Nếu hệ thống hỗ trợ nhiều định dạng hash do lịch sử, bản ghi phải được diễn giải bằng cơ chế đã cấu hình tin cậy. Không chấp nhận việc client chọn một thuật toán yếu hơn hoặc chuyển sang plaintext khi gặp lỗi định dạng.

Sau khi xác minh thành công, hệ thống có thể có quy trình nâng cấu hình lưu trữ theo policy. Đây là việc bảo trì verifier; không được nhầm với việc coi mọi bản ghi chưa nâng cấp là đã kiểm tra hợp lệ.

## 5. Ví dụ Java: mật khẩu khớp mới là kết quả một bước

Đoạn sau minh họa cách phân tách kết quả trong một ứng dụng dùng Spring Security. Các kiểu `AccountRecord`, `StepResult` và repository là kiểu giả định; đây không phải bộ đăng nhập hoàn chỉnh để đưa thẳng vào production.

```java
AccountRecord account = accounts.findByLogin(loginNamespace, loginName);

// dummyEncodedPassword được tạo trước bằng cấu hình phù hợp,
// không encode lại một giá trị mới trong mỗi request.
String encoded = account == null
        ? dummyEncodedPassword
        : account.encodedPassword();

boolean passwordMatches = passwordEncoder.matches(rawPassword, encoded);

if (account == null || !passwordMatches || !account.canAuthenticate()) {
    return StepResult.genericFailure();
}

// Kết quả nội bộ, không phải phiên có đầy đủ quyền.
return StepResult.passwordStepVerified(account.subjectId());
```

Spring Security mô tả việc dùng password hash giả khi không tìm thấy user để giảm khác biệt thời gian do bỏ qua phép kiểm tra tốn tài nguyên. Điều đó không bảo đảm toàn bộ request có thời gian tuyệt đối như nhau; truy vấn dữ liệu, định dạng hash và các nhánh khác vẫn cần xem xét. [Spring Security — Preventing Timing Attacks](https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html#_preventing_timing_attacks).

Trong ví dụ, caller chỉ được dùng `passwordStepVerified` như sự kiện nội bộ. Nếu còn yêu cầu MFA, nó phải tạo giao dịch tiếp theo có quyền giới hạn và gắn với đúng subject. Không nhận lại cùng trạng thái dưới dạng boolean do client khai rồi coi đó là proof.

Ví dụ chưa thể hiện rate limiting, xử lý exception, audit, quản lý giao dịch, chống lạm dụng và phát hành phiên. Khi dùng framework thực tế, cần kiểm soát các điểm mở rộng mà không vô tình bỏ qua đường xác thực đã được framework bảo vệ.

## 6. OTP: đúng mã còn phải đúng thời điểm và trạng thái sử dụng

Mã dùng một lần cần được kiểm tra trong phạm vi tài khoản, mục đích và trạng thái tương ứng. Thời hạn, giới hạn số lần thử và chống dùng lại bổ sung cho việc so khớp mã. TOTP còn phụ thuộc nguồn thời gian và seed được bảo vệ. Seed phải dùng được để tính mã, nên không thể xử lý như password hash một chiều. [OWASP Multifactor Authentication Cheat Sheet — OTP Handling](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#one-time-password-otp-handling-and-storage).

Ví dụ, máy chủ phát một mã cho giao dịch đăng nhập của An. Một request dùng mã đó để thay email, hoặc để hoàn tất giao dịch khác không được phép, phải bị từ chối theo ràng buộc của cơ chế. Giá trị số giống nhau không chứng minh hai giao dịch tương đương.

Với TOTP, một time step có thể tạo cùng mã trong nhiều request. Việc kiểm tra mã còn trong cửa sổ chấp nhận không tự ngăn replay. Cần phối hợp trạng thái đã chấp nhận theo thiết kế, kể cả khi nhiều instance xử lý đồng thời.

Mã ngắn có không gian đoán nhỏ. Hash một mã ngắn không tự làm nó chống được mọi tấn công ngoại tuyến nếu dữ liệu xác minh bị lộ. Không ghi mã, seed hoặc recovery code vào log để “dễ debug”.

## 7. Phản hồi mật mã: kiểm tra nội dung và ngữ cảnh đã ký

Trong cơ chế challenge–response, máy chủ đưa ra challenge và kiểm tra proof gắn với challenge đó. Với WebAuthn, việc kiểm tra assertion bao gồm các điều kiện như challenge, origin, RP ID, cờ hiện diện/xác minh người dùng khi áp dụng và chữ ký với public key đã đăng ký. Chỉ tìm thấy credential ID trong database là chưa đủ. [W3C WebAuthn Level 2 — Verifying an Authentication Assertion](https://www.w3.org/TR/webauthn-2/#sctn-verifying-assertion).

Ví dụ, ứng dụng có hai môi trường thử nghiệm độc lập. Một phản hồi được tạo cho giao dịch ở môi trường A không nên được chấp nhận tùy tiện ở B chỉ vì người dùng có tên giống nhau. Những ràng buộc về relying party và giao dịch là một phần của ý nghĩa proof.

Xác minh mật mã nên do thư viện giao thức phù hợp thực hiện. Việc tự chọn một vài field, ghép chuỗi rồi kiểm tra chữ ký có thể bỏ sót dữ liệu mà giao thức yêu cầu kiểm tra. Thư viện cũng cần được cấu hình đúng nguồn khóa và policy.

## 8. Token: đọc được không có nghĩa là được chấp nhận

Một JWT có thể được decode để đọc payload mà chưa xác minh tính toàn vẹn. Việc chấp nhận cần quy tắc của loại token và giao thức: thuật toán cho phép, nguồn khóa tin cậy, issuer, audience và các điều kiện liên quan. Các loại JWT khác mục đích cần quy tắc xác minh phù hợp để tránh dùng nhầm token. [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html).

Trong một thiết kế minh họa, token chỉ dành cho chức năng xác nhận email không được dùng thay token truy cập hồ sơ. Chữ ký hợp lệ chỉ là một phần: ứng dụng còn phải biết token ấy được phát cho ai, để làm gì và có được chấp nhận tại endpoint hiện tại không.

Với token tham chiếu, ứng dụng cần tra cứu hoặc dùng dịch vụ xác minh tin cậy theo kiến trúc. Không thể kiểm tra một token không tự mô tả bằng cách chỉ nhìn độ dài chuỗi hoặc sự tồn tại của header `Authorization`.

Một bearer token bị đánh cắp có thể được người khác trình lên. Vì vậy, kết quả token hợp lệ không tự là một lần chứng minh mới rằng người trình còn kiểm soát authenticator ban đầu. Cần phân biệt kiểm tra token của phiên với thực hiện xác thực mới.

## 9. Trạng thái tài khoản và trạng thái credential

Một proof có thể đúng về mặt kỹ thuật nhưng yêu cầu vẫn không được hoàn tất. Ví dụ, tài khoản đã bị disable, credential đã bị thu hồi hoặc giao dịch đã hết hiệu lực.

| Tình huống minh họa | Kết quả cần phân biệt |
|---|---|
| Mật khẩu khớp, tài khoản hoạt động, còn yêu cầu MFA | Một bước hợp lệ; chưa phải đăng nhập đầy đủ |
| Mật khẩu khớp, tài khoản đã bị disable | Không tạo khả năng truy cập trái trạng thái tài khoản |
| Chữ ký kiểm tra đúng nhưng khóa đã bị thu hồi | Không chỉ dựa vào phép kiểm tra chữ ký |
| OTP đúng nhưng giao dịch đã hoàn tất | Không cho sử dụng proof lại ngoài thiết kế |
| Token còn hạn nhưng sai mục đích | Không chấp nhận tại endpoint hiện tại |
| Mọi yếu tố hợp lệ nhưng thiếu quyền với tài nguyên | Xác thực có thể đạt; authorization vẫn từ chối |

Trạng thái có thể đổi trong lúc xử lý. Giả sử quản trị viên disable tài khoản khi request đăng nhập đang kiểm tra mật khẩu. Nếu đường phát hành phiên chỉ dựa vào snapshot đầu tiên, cần đánh giá nguy cơ vẫn tạo phiên sau thời điểm disable.

Không phải mọi kiểm tra đều phải ở cùng một database transaction. Tuy nhiên, thiết kế phải nêu thời điểm nào là quyết định cuối và cách xử lý sự kiện thu hồi, vô hiệu hóa hoặc thay credential đang diễn ra.

## 10. Thất bại xác minh không được trở thành đường dò thông tin

Phản hồi lỗi có thể tiết lộ tài khoản tồn tại, tài khoản bị khóa hay một phần credential đã đúng. OWASP khuyến nghị xem xét đồng thời thông báo, mã phản hồi và khác biệt thời gian để hạn chế enumeration. [OWASP Authentication Cheat Sheet — Authentication and Error Messages](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#authentication-and-error-messages).

Thông báo phía người dùng có thể được chuẩn hóa, trong khi audit nội bộ vẫn lưu mã nguyên nhân phù hợp cho vận hành. Không trả nguyên thông tin “user tồn tại nhưng password hash không khớp” từ exception cho client chưa xác thực.

Nếu kho dữ liệu, KMS hoặc dịch vụ xác minh bị lỗi, đó không phải bằng chứng hợp lệ. Thiết kế có thể trả lỗi tạm thời hoặc theo một đường dự phòng đã được kiểm soát; không tự bỏ qua MFA hay chấp nhận credential vì dependency không sẵn sàng.

Rate limiting cũng cần gắn với bối cảnh. Một giới hạn theo IP duy nhất có thể không phản ánh việc nhiều nguồn cùng thử một tài khoản. Ngược lại, khóa vô thời hạn theo username do client khai có thể bị lợi dụng để chặn người dùng thật. Chính sách phải cân bằng mục tiêu chống đoán với khả năng phục hồi.

## 11. Quan sát và kiểm thử kết quả đúng phạm vi

Audit hữu ích có thể ghi mã giao dịch, subject nội bộ nếu đã xác định, loại phương tiện xác thực, kết quả từng bước và nguyên nhân nội bộ được kiểm soát. Tránh đưa mật khẩu, OTP, private key, seed, session token hoặc access token thô vào log và tracing.

Đối với kết quả thành công, cần có đủ ngữ cảnh để bước tiếp theo biết đã kiểm tra phương thức nào và khi nào. Không nên gom mọi trường hợp thành một cờ `authenticated=true` rồi để các API tự đoán mức hoàn tất.

Bộ ca kiểm thử nền tảng có thể gồm:

| Nhóm | Ca minh họa | Điều cần chứng minh |
|---|---|---|
| Thành công | Proof hợp lệ, đủ policy | Tạo đúng trạng thái cho đúng subject |
| Không tồn tại | Định danh không có trong namespace | Không tạo tài khoản hoặc lộ chi tiết ngoài policy |
| Sai proof | Mật khẩu hoặc phản hồi không đúng | Không tạo phiên đủ quyền |
| Sai liên kết | Proof của A được dùng cho B | Không chuyển kết quả sang subject khác |
| Hết hiệu lực | Mã hết hạn, credential bị thu hồi | Không chấp nhận chỉ vì từng hợp lệ |
| Replay | Dùng lại proof dùng một lần | Không có lần chấp nhận mới trái contract |
| Đồng thời | Hai request cùng tiêu thụ proof | Trạng thái được phối hợp đúng |
| Thiếu MFA | Chỉ vượt bước đầu | Không gọi được chức năng yêu cầu hoàn tất |
| Dependency lỗi | Validator không trả kết quả tin cậy | Không hạ yêu cầu để cho qua |
| Dữ liệu nhạy cảm | Quan sát log và báo cáo lỗi | Không lưu proof hoặc bí mật thô ngoài thiết kế |

Các ca trên là gợi ý học tập, không phải schema bắt buộc. Cần thêm ca cho cơ chế thật và các đường đi dự phòng của ứng dụng.

Mock trả `true` giúp kiểm tra phản ứng sau kết quả đã cho, nhưng không chứng minh password encoder, kho trạng thái OTP hay validator token hoạt động đúng. Khi cần xác minh tích hợp, phải dùng thành phần thực phù hợp trong môi trường thử nghiệm và dữ liệu đã kiểm soát.

## 12. Tự kiểm tra cách hiểu

**Username đúng và mật khẩu không rỗng có đủ xác thực không?**

Không. Cần kiểm tra proof bằng cơ chế phù hợp và hoàn tất các điều kiện còn lại.

**Vì sao không encode lại mật khẩu rồi so chuỗi với hash đã lưu?**

Vì một lần encode mới có thể dùng salt mới. Hãy dùng API kiểm tra theo bản hash đã lưu.

**Mã TOTP còn nằm trong cửa sổ thời gian có luôn được dùng lại không?**

Không. Cần kiểm tra điều kiện chống replay và trạng thái đã chấp nhận của cơ chế.

**JWT decode được, có field `sub`, có nghĩa token hợp lệ không?**

Không. Đọc payload không thay việc xác minh mật mã, nguồn phát hành, mục đích và các điều kiện của loại token.

**Credential hợp lệ có cho phép bỏ kiểm tra tenant và quyền không?**

Không. Credential verification cung cấp cơ sở xác thực; authorization quyết định hành động trên tài nguyên.

