# Password credential

> **Chương:** Credential  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS  
> **Trọng tâm:** Mật khẩu với vai trò bằng chứng xác thực: cách tạo lập, lưu trữ, kiểm tra, sử dụng và thu hồi; các giới hạn khi bảo vệ danh tính và tài nguyên.

## 1. Password credential là gì?

**Password credential** là một bí mật mà người dùng biết và dùng để chứng minh quyền kiểm soát tài khoản khi đăng nhập hoặc thực hiện hành động cần xác thực lại. Hệ thống thường nhận một **định danh tài khoản** (ví dụ username) và **mật khẩu**, sau đó so sánh mật khẩu người dùng cung cấp với thông tin xác minh đã lưu.

Trong mô hình xác thực, hãy phân biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Identifier** | Dùng để tìm tài khoản, không tự chứng minh danh tính | Username, email đăng nhập |
| **Password** | Bí mật người dùng biết và có thể nhập lại | Một cụm mật khẩu dài |
| **Password verifier** | Dữ liệu phía máy chủ dùng để kiểm tra mật khẩu mà không cần lưu mật khẩu rõ | Bản băm Argon2id cùng salt và tham số |
| **Authentication** | Quá trình đánh giá bằng chứng và trạng thái tài khoản | Xác minh mật khẩu rồi yêu cầu MFA |
| **Session / token** | Cách duy trì kết quả xác thực cho các yêu cầu tiếp theo | Cookie phiên hoặc access token |
| **Authorization** | Quyết định một chủ thể được thực hiện hành động nào trên tài nguyên nào | Được đọc hồ sơ của chính mình |

Mật khẩu là yếu tố thuộc nhóm **“điều bạn biết” (something you know)**. Chứng minh biết mật khẩu **không chứng minh tuyệt đối** người nhập là chủ tài khoản: mật khẩu có thể bị đánh cắp, bị đoán hoặc được chia sẻ. Vì thế, hệ thống không nên coi một lần nhập mật khẩu đúng là bằng chứng bất biến cho mọi hành động về sau.

**Mục tiêu của bài** là hiểu cách biến mật khẩu thành một phương thức xác thực có kiểm soát và hiểu chính xác những rủi ro mà mật khẩu không thể tự giải quyết.

## 2. Vị trí của mật khẩu trong ranh giới tin cậy

Một luồng đăng nhập cơ bản có hai phía: **client**, nơi người dùng nhập mật khẩu, và **dịch vụ xác thực**, nơi thực hiện kiểm tra đáng tin cậy. Client có thể bị kiểm soát hoặc mô phỏng bởi người khác; không được tin thông báo “mật khẩu đã đúng” do client tự gửi.

~~~mermaid
flowchart LR
    U["Người dùng"] -->|"Nhập mật khẩu"| C["Client: trình duyệt / ứng dụng"]
    C -->|"HTTPS: identifier + password"| A["Dịch vụ xác thực tin cậy"]
    A --> V["Tra verifier, kiểm tra bằng KDF"]
    V --> Q{"Hợp lệ và tài khoản được phép?"}
    Q -->|"Không"| N["Từ chối, giới hạn thử sai"]
    Q -->|"Có"| M{"Có yêu cầu MFA / step-up?"}
    M -->|"Có"| F["Kiểm tra yếu tố bổ sung"]
    M -->|"Không"| S["Cấp phiên / token"]
    F -->|"Thành công"| S
    F -->|"Thất bại"| N
    S --> R["API tiếp tục kiểm tra phiên/token và quyền tài nguyên"]
~~~

Một số ranh giới cần nhớ:

1. **Thiết bị người dùng → máy chủ:** dùng TLS/HTTPS để bảo vệ mật khẩu trên đường truyền. TLS không ngăn trang phishing hoặc phần mềm độc hại trên thiết bị thu mật khẩu.
2. **Máy chủ ứng dụng → kho dữ liệu:** lưu password verifier bằng cơ chế băm mật khẩu phù hợp; không giữ mật khẩu ở dạng đọc được.
3. **Dịch vụ xác thực → dịch vụ tài nguyên:** chuyển tiếp phiên/token có giới hạn và kiểm tra chính sách truy cập độc lập với việc mật khẩu đúng.
4. **Đăng nhập → khôi phục tài khoản:** luồng đặt lại mật khẩu cần bằng chứng và điều kiện riêng; không thể cho phép một đường khôi phục yếu vượt qua mức bảo vệ của đăng nhập.

### Ví dụ gần thực tế

Một nhân viên nhập đúng mật khẩu để vào cổng nội bộ. Sau đăng nhập, họ thử gọi API lấy hồ sơ lương của đồng nghiệp bằng cách thay ID trong URL. API vẫn phải kiểm tra **quyền đối với hồ sơ cụ thể**; trạng thái “password verified” chỉ góp phần xác định danh tính, không cấp quyền truy cập toàn bộ dữ liệu.

## 3. Chu kỳ sống của password credential

Mật khẩu cũng có vòng đời riêng bên trong vòng đời tài khoản.

~~~mermaid
stateDiagram-v2
    [*] --> ChuaThietLap: Tạo tài khoản / lời mời
    ChuaThietLap --> DangSuDung: Thiết lập mật khẩu hợp lệ
    DangSuDung --> DangSuDung: Xác minh khi đăng nhập
    DangSuDung --> DaThayThe: Đổi mật khẩu
    DaThayThe --> DangSuDung: Verifier mới có hiệu lực
    DangSuDung --> CanDatLai: Quên hoặc nghi lộ
    CanDatLai --> DangSuDung: Khôi phục có kiểm soát
    DangSuDung --> ThuHoi: Vô hiệu hóa tài khoản / bỏ đăng nhập mật khẩu
    ThuHoi --> [*]
~~~

| Giai đoạn | Việc hệ thống cần bảo vệ | Lỗi thường gặp |
|---|---|---|
| **Thiết lập** | Chấp nhận mật khẩu đủ mạnh và không nằm trong danh sách đã lộ | Bắt dùng mẫu dễ đoán hoặc giới hạn độ dài quá ngắn |
| **Lưu verifier** | Băm bằng thuật toán chuyên dụng, salt riêng, tham số phù hợp | Lưu plaintext, mã hóa có thể giải ngược hoặc SHA-256 trực tiếp |
| **Đăng nhập** | Kiểm tra mật khẩu, trạng thái tài khoản và hạn chế thử sai | Cho dò đoán vô hạn, phân biệt tài khoản tồn tại |
| **Đổi mật khẩu** | Chứng minh quyền kiểm soát tài khoản và ý định thay đổi | Chỉ dựa vào phiên đã bị đánh cắp |
| **Đặt lại** | Token khôi phục có thời hạn, đúng mục đích, một lần | Token yếu hoặc có thể dùng lại |
| **Thu hồi** | Vô hiệu hóa verifier cũ, rà soát phiên và token | Đã đổi mật khẩu nhưng phiên kẻ tấn công vẫn còn hiệu lực |

Không nên dùng cùng một mật khẩu hoặc verifier cho nhiều tài khoản do cùng một dịch vụ tự cấp. Mỗi tài khoản phải có salt độc lập; cùng một mật khẩu do hai người chọn cũng nên cho ra hai bản ghi verifier khác nhau.

## 4. Chính sách tạo mật khẩu: ưu tiên độ dài và mật khẩu chưa bị lộ

Người dùng thường gặp các quy tắc như “phải có một chữ hoa, một số, một ký tự đặc biệt”. Quy tắc cấu tạo quá cứng dễ dẫn đến mẫu đoán được như thêm \`1!\` vào cuối từ quen thuộc. Một chính sách tốt cần xem xét **độ dài**, **khả năng bị đoán**, **mật khẩu đã bị lộ**, cùng với trải nghiệm người dùng.

### Các nguyên tắc thiết kế

- **Ưu tiên mật khẩu dài hoặc cụm mật khẩu (passphrase):** hỗ trợ mật khẩu đủ dài, kể cả khoảng trắng, và công khai giới hạn kỹ thuật nếu có. Chọn ngưỡng tối thiểu phù hợp chuẩn áp dụng và việc có hay không có MFA.
- **Chặn mật khẩu đã bị lộ hoặc thường dùng:** so sánh với danh sách mật khẩu bị xâm phạm, biến thể quá phổ biến và giá trị dễ suy ra từ ngữ cảnh; thiết kế cách tra cứu không tiết lộ mật khẩu đến dịch vụ bên ngoài.
- **Cho phép trình quản lý mật khẩu:** hỗ trợ dán (paste), autofill và mật khẩu được tạo ngẫu nhiên. Cấm dán thường làm người dùng chọn mật khẩu dễ nhớ và yếu hơn.
- **Tránh buộc đổi định kỳ vô cớ:** yêu cầu đổi khi có dấu hiệu lộ, rủi ro cụ thể hoặc quy định áp dụng; việc đổi thường xuyên mà không có nguyên nhân có thể thúc đẩy các biến thể dễ đoán.
- **Không đặt quy tắc “bí mật” ở client:** có thể kiểm tra để hướng dẫn ngay trên giao diện, nhưng server phải kiểm tra lại chính sách.
- **Xử lý Unicode nhất quán:** cùng một chuỗi ký tự phải được mã hóa/chuẩn hóa theo chính sách rõ ràng lúc tạo và lúc kiểm tra; tránh âm thầm cắt bớt hoặc biến đổi mật khẩu làm người dùng khó hiểu.

Ví dụ, cụm \`Con meo ngu tren ghe xanh\` dài hơn một mật khẩu ngắn có ký tự đặc biệt, nhưng **không mặc nhiên mạnh** nếu đó là câu phổ biến mà kẻ tấn công có thể đoán. Trình quản lý mật khẩu sinh chuỗi độc lập cho từng dịch vụ thường là lựa chọn tốt; passphrase nên gồm các từ được chọn đủ ngẫu nhiên.

### Những điều không nên làm

| Thực hành | Vì sao có vấn đề | Cách thay |
|---|---|---|
| Chỉ chấp nhận 8 ký tự hoặc cắt mật khẩu dài hơn | Giảm không gian lựa chọn và có thể tạo trùng mật khẩu ngoài ý muốn | Hỗ trợ độ dài lớn, xử lý giới hạn KDF an toàn |
| Cấm khoảng trắng hoặc ký tự “lạ” không có lý do | Loại bỏ passphrase và nhiều ngôn ngữ | Công bố bảng ký tự/giới hạn kỹ thuật thực sự cần thiết |
| Gợi ý “TênCôngTy@2026” cho mọi nhân viên | Tạo mẫu chung dễ đoán | Dùng mật khẩu riêng, ngẫu nhiên hoặc passphrase |
| Gửi lại mật khẩu cũ qua email | Đòi hỏi hệ thống có thể lấy lại mật khẩu rõ | Cung cấp luồng đặt lại mật khẩu an toàn |
| Ép đổi mật khẩu hàng tháng mà không xét rủi ro | Người dùng dễ dùng quy luật tăng số cuối | Đổi khi nghi lộ, dùng cơ chế giám sát và MFA |
| Dùng gợi ý mật khẩu chứa một phần bí mật | Làm lộ manh mối cho kẻ tấn công | Dùng trình quản lý mật khẩu và khôi phục có kiểm soát |

## 5. Không bao giờ lưu mật khẩu dạng rõ

Máy chủ **không cần biết lại mật khẩu gốc** để kiểm tra người dùng có nhập đúng hay không. Hệ thống nên tạo **password verifier** bằng hàm dẫn xuất khóa/băm mật khẩu chuyên dụng (password hashing/KDF) với **salt ngẫu nhiên riêng** cho từng mật khẩu.

### Vì sao SHA-256 trực tiếp không đủ?

Hàm băm thông thường như SHA-256 được thiết kế chạy nhanh. Nếu cơ sở dữ liệu rò rỉ, kẻ tấn công có thể thử rất nhiều mật khẩu ứng viên ngoại tuyến rồi so khớp nhanh với bản băm đã lấy được. Mật khẩu của con người thường có entropy thấp hơn khóa ngẫu nhiên, nên tốc độ đoán là vấn đề lớn.

Hàm băm mật khẩu như **Argon2id**, **scrypt** hoặc **bcrypt** được thiết kế làm cho mỗi lần thử đoán tốn tài nguyên hơn. **Argon2id** hỗ trợ cấu hình chi phí bộ nhớ và thời gian; các tham số cụ thể cần được chọn theo khả năng máy chủ, tải đăng nhập và mức bảo mật mong muốn. Khi sử dụng bcrypt, cần chú ý giới hạn đầu vào theo **byte**, tránh cắt mật khẩu âm thầm.

### Salt, hash và pepper khác nhau ra sao?

| Thành phần | Bí mật? | Mục đích |
|---|---|---|
| **Password** | Có | Bằng chứng mà người dùng biết |
| **Salt** | Không | Giá trị ngẫu nhiên riêng cho verifier, khiến cùng mật khẩu không nhất thiết cho cùng bản băm |
| **Password hash/KDF output** | Cần bảo vệ | Thông tin để máy chủ kiểm tra mật khẩu; nếu bị lộ vẫn có thể chịu tấn công đoán ngoại tuyến |
| **Work factor / KDF parameters** | Không | Quy định chi phí cho mỗi lần băm và kiểm tra |
| **Pepper (tùy chọn)** | Có | Bí mật bổ sung lưu tách khỏi kho verifier, tăng rào cản khi chỉ CSDL bị lộ |

Ví dụ dạng bản ghi minh họa:

~~~text
account_id: 824
password_verifier: <algorithm-and-parameters>$<salt>$<derived-hash>
password_updated_at: 2026-11-22T05:00:00Z
~~~

Giá trị trên là **hình thức khái niệm**, không phải định dạng lưu trữ bắt buộc; nhiều thư viện mã hóa sẵn thuật toán, salt và tham số trong một chuỗi chuẩn của riêng thư viện. **Không lưu thêm cột \`password_plaintext\`** để kiểm tra, gửi lại hoặc hỗ trợ khách hàng.

### Quy trình tạo verifier

~~~text
Người dùng thiết lập password
    |
    v
Server kiểm tra chính sách và danh sách mật khẩu rủi ro
    |
    v
Sinh salt ngẫu nhiên riêng cho password
    |
    v
verifier = PasswordKDF(password, salt, params)
    |
    v
Lưu {algorithm, params, salt, verifier} bằng cơ chế có kiểm soát
    |
    v
Xóa tham chiếu plaintext sớm khi có thể; không ghi log password
~~~

Một số hệ thống sử dụng **pepper** đặt trong HSM/KMS hoặc dịch vụ bí mật tách khỏi cơ sở dữ liệu. Pepper phải được quản lý như một bí mật thực sự, có kế hoạch xoay vòng và khôi phục sau sự cố. Pepper là lớp bổ sung, **không thay thế** salt và KDF chuyên dụng.

### Điều chỉnh tham số và nâng cấp thuật toán

Chi phí KDF quá thấp giúp kẻ tấn công thử mật khẩu nhanh hơn khi verifier rò rỉ; chi phí quá cao có thể tạo điểm nghẽn hoặc bị lợi dụng làm cạn tài nguyên server. Vì vậy cần đo tải thực tế, giới hạn số phép kiểm tra đồng thời và xem xét năng lực hệ thống. Có thể lưu phiên bản thuật toán/tham số trong bản ghi để **nâng cấp verifier sau lần đăng nhập thành công**, khi đã biết mật khẩu hiện tại trong phạm vi xử lý ngắn hạn.

Không tự thiết kế “hàm băm mật khẩu” bằng cách ghép nhiều vòng SHA-256, MD5 hoặc mã hóa tùy biến. Dùng thư viện mật mã được duy trì tốt, với cấu hình và cơ chế kiểm tra đầu vào đã được xem xét.

## 6. Xác minh mật khẩu khi đăng nhập

Trong một yêu cầu đăng nhập, máy chủ cần:

1. Nhận định danh và mật khẩu qua HTTPS; không đưa mật khẩu vào URL, query string hay log.
2. Áp dụng giới hạn lưu lượng và kiểm soát thử sai theo ngữ cảnh.
3. Tìm tài khoản và verifier tương ứng, nhưng tránh tiết lộ tài khoản có tồn tại chỉ qua nội dung lỗi hoặc thời gian phản hồi dễ phân biệt.
4. Tính/kiểm tra KDF bằng thư viện chuyên dụng, có chống rò rỉ qua phép so sánh không an toàn.
5. Đánh giá trạng thái tài khoản: đã kích hoạt, chưa bị vô hiệu hóa hay đình chỉ; có ràng buộc về thiết bị hoặc truy cập không.
6. Yêu cầu yếu tố bổ sung nếu chính sách MFA hoặc thao tác nhạy cảm đòi hỏi.
7. Chỉ sau khi các điều kiện hoàn tất mới phát hành hoặc nâng mức tin cậy của phiên/token.
8. Ghi nhận sự kiện ở mức cần thiết nhưng không ghi mật khẩu hoặc giá trị verifier.

### Mã giả mô tả trách nhiệm của backend

~~~typescript
// Pseudocode: những hàm bảo mật ở đây là thành phần tin cậy
// cần dùng thư viện và chính sách đã kiểm định khi triển khai thật.
async function login(identifier, password, requestContext) {
  await enforceLoginRateLimits(identifier, requestContext);

  const account = await findAccountForLogin(identifier);
  const verifier = account?.passwordVerifier ?? DUMMY_VERIFIER;
  const matched = await passwordHasher.verify(password, verifier);

  // DUMMY_VERIFIER giúp giảm khác biệt nhánh xử lý tồn tại/không tồn tại;
  // không bảo đảm triệt tiêu mọi kênh phụ và cần cân nhắc chi phí KDF.
  if (!account || !matched || account.status !== "ACTIVE") {
    await recordLoginFailureSafely(identifier, requestContext);
    return genericAuthenticationFailure();
  }

  if (await needsMfa(account, requestContext)) {
    return createShortLivedMfaChallenge(account.id, requestContext);
  }

  const session = await issueNewSession(account.id, requestContext);
  return session;
}
~~~

**Không cấp phiên đầy đủ trước khi vượt qua bước MFA bắt buộc.** Nếu dùng phiên tạm thời để thực hiện challenge MFA, phiên đó chỉ được phép gọi các endpoint cần thiết cho challenge, có giới hạn thời gian và chống phát lại.

Phép so sánh verifier nên được cung cấp bởi thư viện được chọn; triển khai tự viết dễ mắc lỗi thời gian chạy không đồng đều, xử lý encoding sai hoặc chọn tham số không an toàn. Một giao diện cũng không nên cho phép người dùng gửi sẵn cờ \`passwordValid=true\` để backend tin theo.

## 7. Ba nhóm tấn công đối với mật khẩu

Mô hình đe dọa cần phân biệt **đoán trực tuyến**, **đoán ngoại tuyến** và **đánh cắp trực tiếp**.

| Nhóm tấn công | Cách thực hiện | Biện pháp giảm rủi ro chủ yếu |
|---|---|---|
| **Online guessing / brute force** | Gửi nhiều mật khẩu ứng viên vào endpoint đăng nhập | Giới hạn tốc độ, chống bot, giám sát, MFA, tín hiệu rủi ro |
| **Password spraying** | Thử một vài mật khẩu phổ biến với nhiều tài khoản | Theo dõi mẫu trên nhiều tài khoản/IP, kiểm tra mật khẩu lộ, xác thực mạnh |
| **Credential stuffing** | Dùng cặp username/mật khẩu rò rỉ từ dịch vụ khác | Chặn mật khẩu đã lộ, MFA/passkey, giám sát bất thường |
| **Offline cracking** | Đánh cắp password verifier rồi thử mật khẩu trên máy kẻ tấn công | Salt riêng, KDF chi phí phù hợp, bảo vệ CSDL và bí mật bổ sung |
| **Phishing** | Giả trang đăng nhập để người dùng nhập mật khẩu | Passkey/WebAuthn chống phishing, nhận diện miền, MFA thích hợp |
| **Malware / keylogger** | Đọc mật khẩu lúc người dùng nhập hoặc lấy từ thiết bị | Bảo vệ thiết bị, quản lý phiên, giảm phụ thuộc vào mật khẩu |
| **Replay** | Sử dụng lại bí mật đã lấy được để đăng nhập | Không dùng chung mật khẩu, MFA, kiểm soát rủi ro, khôi phục/thu hồi |
| **Account enumeration** | Dò tài khoản tồn tại qua phản hồi hoặc thời gian xử lý | Thông điệp lỗi phù hợp, điều tiết tốc độ, giảm chênh lệch luồng |

### Điều cần hiểu về phishing và replay

Một mật khẩu là **bí mật có thể tái sử dụng**. Nếu kẻ tấn công biết mật khẩu, họ có thể nhập nó nhiều lần cho đến khi mật khẩu bị đổi hoặc có các lớp bảo vệ khác. HTTPS chỉ giúp chống nghe lén đường truyền; nó không ngăn người dùng tự nhập mật khẩu vào một trang giả mạo.

OTP qua SMS hoặc ứng dụng TOTP tăng rào cản so với mật khẩu đơn lẻ, nhưng vẫn có thể bị phishing thời gian thực khi kẻ gian chuyển tiếp mã ngay lúc người dùng nhập. **Passkey/WebAuthn** sử dụng chứng minh mật mã gắn với nguồn gốc (origin) dịch vụ nên có khả năng chống dạng phishing này tốt hơn. Nếu tài nguyên có rủi ro cao, nên đánh giá phương thức chống phishing và cơ chế xác thực tăng cường thay vì chỉ dựa vào mật khẩu.

### Chống lạm dụng mà không tự tạo từ chối dịch vụ

Giới hạn số lần thử theo IP đơn lẻ là chưa đủ vì bot có thể phân tán yêu cầu. Tương tự, khóa vĩnh viễn tài khoản sau vài lần sai có thể cho phép kẻ tấn công khóa tài khoản của người khác. Một thiết kế thường kết hợp:

- Theo dõi theo tài khoản, nguồn truy cập và mẫu hành vi.
- Giới hạn tốc độ thích ứng và thời gian chờ hợp lý.
- MFA hoặc challenge bổ sung cho trường hợp rủi ro.
- Thông báo hoạt động bất thường qua kênh an toàn.
- Quản lý tải của phép tính KDF để endpoint đăng nhập không thành điểm cạn kiệt CPU/bộ nhớ.

Khi ghi log, giữ dữ liệu phục vụ điều tra ở mức cần thiết, tránh lưu mật khẩu, mã OTP, token hoặc dữ liệu định danh vượt nhu cầu.

## 8. Đổi mật khẩu và đặt lại mật khẩu khác nhau thế nào?

**Đổi mật khẩu (change password)** thường xuất phát từ người dùng đang kiểm soát tài khoản. **Đặt lại mật khẩu (reset password)** diễn ra khi người dùng không thể cung cấp mật khẩu hiện tại hoặc phải khôi phục từ tình huống nghi lộ. Hai luồng có điều kiện xác thực khác nhau.

### Đổi mật khẩu khi đang đăng nhập

Các bước tham khảo:

1. Kiểm tra phiên hiện tại và chính sách cho phép người dùng đổi credential.
2. Yêu cầu xác thực lại bằng mật khẩu hiện tại hoặc phương thức mạnh phù hợp, đặc biệt với phiên đã lâu hoặc dấu hiệu rủi ro.
3. Kiểm tra mật khẩu mới bằng chính sách hiện hành; từ chối mật khẩu đã lộ hoặc không đủ điều kiện.
4. Tạo verifier mới với salt mới, lưu bằng giao dịch có kiểm soát và đánh dấu verifier cũ không còn hiệu lực.
5. Xem xét thu hồi các phiên/refresh token cũ, nhất là khi đổi do nghi bị chiếm quyền.
6. Gửi thông báo thay đổi qua kênh phù hợp, không đưa mật khẩu mới vào thông báo.

### Đặt lại mật khẩu khi quên

~~~mermaid
sequenceDiagram
    participant U as Người yêu cầu
    participant A as Dịch vụ xác thực
    participant M as Kênh khôi phục
    U->>A: Yêu cầu đặt lại (identifier)
    A-->>U: Phản hồi trung tính, không tiết lộ tài khoản
    A->>M: Gửi mã/liên kết ngắn hạn nếu đủ điều kiện
    M-->>U: Nhận mã qua kênh khôi phục
    U->>A: Gửi mã và mật khẩu mới qua HTTPS
    A->>A: Kiểm tra purpose, hạn, trạng thái, chống dùng lại
    A->>A: Ghi verifier mới và tiêu thụ mã nguyên tử
    A-->>U: Xác nhận và yêu cầu đăng nhập lại theo chính sách
~~~

**Token khôi phục** phải đủ ngẫu nhiên, có thời hạn ngắn, gắn đúng tài khoản và mục đích, không được dùng lại sau khi tiêu thụ. Có thể lưu hash của token để hạn chế rò rỉ. Mọi thao tác sử dụng token cần được xác minh ở server; tránh nhúng thông tin bí mật vào URL của các công cụ bên thứ ba hoặc để lộ token trong log, referrer và hệ thống phân tích.

Đặt lại mật khẩu **không mặc nhiên khôi phục** một tài khoản đang bị đình chỉ vì sự cố hay đã vô hiệu hóa theo quy trình nhân sự. Trước khi chấp nhận, phải kiểm tra trạng thái tài khoản và mức bảo đảm cần thiết. Với tài khoản quan trọng, việc chỉ sở hữu hộp thư chưa chắc đủ để được phép thay mật khẩu hoặc tắt MFA.

### Vấn đề phiên sau khi đổi hoặc reset

Mật khẩu mới thay thế verifier cũ nhưng **không tự động vô hiệu** mọi phiên hoặc token đã phát hành. Chúng là các bằng chứng truy cập khác với password credential. Hệ thống cần có chiến lược cụ thể đối với session server-side, refresh token, access token chưa hết hạn, phiên SSO và thiết bị được ghi nhớ.

Khi nghi bị chiếm quyền, chỉ buộc đổi mật khẩu là chưa đủ nếu kẻ tấn công đã thêm passkey, thay email khôi phục hoặc giữ phiên riêng. Cần rà soát các credential, liên kết danh tính và quyền được chỉnh sửa gần đây.

## 9. Mật khẩu trong một hệ thống có MFA, passkey và SSO

Password credential hiếm khi đứng độc lập trong một nền tảng hiện đại. Việc chọn nó phải dựa vào mức bảo vệ tài nguyên và rủi ro.

| Bối cảnh | Vai trò của mật khẩu | Điểm cần thiết kế |
|---|---|---|
| Ứng dụng thông thường | Yếu tố đăng nhập chính | KDF tốt, chống dò đoán, bảo vệ phiên |
| Mật khẩu + TOTP | Một trong hai yếu tố | Không cấp phiên đầy đủ trước MFA; chống phishing thời gian thực |
| Mật khẩu + passkey | Có thể là phương thức bổ sung hoặc đường dự phòng | Không để đường mật khẩu yếu làm mất hiệu quả bảo vệ của passkey |
| Đăng nhập bằng IdP/SSO | Có thể do nhà cung cấp danh tính quản lý | Ứng dụng kiểm tra token/phiên liên kết, không cần tự thu mật khẩu IdP |
| Tài khoản quản trị | Có thể bị hạn chế hoặc yêu cầu step-up mạnh | Ưu tiên xác thực chống phishing, kiểm soát thao tác nhạy cảm |
| Tài khoản dịch vụ | Thường không nên dùng mật khẩu tương tác của con người | Dùng danh tính công việc, khóa ngắn hạn hoặc chứng chỉ phù hợp |

Không được coi **ID token** của OpenID Connect là mật khẩu hoặc access token tùy ý. Các token phục vụ mục đích khác nhau; dịch vụ tài nguyên vẫn phải kiểm tra tính hợp lệ và quyền truy cập. Nếu dùng SSO, ứng dụng không nên yêu cầu người dùng nhập lại mật khẩu IdP vào biểu mẫu riêng để “xác minh thêm”, vì có thể tạo ra điểm thu thập bí mật không cần thiết.

Việc bảo vệ thao tác như thay tài khoản nhận tiền hoặc cấp quyền quản trị thường cần **step-up authentication** và kiểm tra ý định hành động ở thời điểm gần thao tác. Một mật khẩu đúng từ nhiều giờ trước không nhất thiết đủ bảo đảm cho yêu cầu có rủi ro rất cao.

## 10. Thiết kế lưu trữ và xác minh: ví dụ end-to-end

Giả sử nền tảng học tập có tài khoản học viên, giảng viên và quản trị viên. Học viên đặt mật khẩu khi đăng ký; giảng viên và quản trị viên còn cần MFA. Backend là nơi duy nhất được quyết định xác minh credential và cấp phiên.

### Luồng đăng ký

~~~text
POST /signup
  username, password

Backend:
  1. Kiểm tra quyền tạo tài khoản và chống tạo hàng loạt.
  2. Kiểm tra username và chính sách mật khẩu.
  3. Tạo password verifier bằng PasswordKDF có salt riêng.
  4. Lưu tài khoản với trạng thái chờ kích hoạt nếu cần.
  5. Gửi lời mời hoặc xác minh kênh liên hệ bằng token một lần.
  6. Không trả về password, salt hay verifier trong response.
~~~

### Luồng đăng nhập

~~~text
POST /login
  identifier, password

Backend:
  1. Áp dụng kiểm soát thử sai.
  2. Tìm tài khoản, xác minh password bằng thư viện KDF.
  3. Kiểm tra trạng thái tài khoản.
  4. Kiểm tra MFA nếu vai trò hoặc rủi ro yêu cầu.
  5. Cấp phiên mới, giới hạn thời hạn và mức bảo đảm.
  6. API kiểm tra cả phiên/token lẫn quyền truy cập từng tài nguyên.
~~~

### Luồng thay đổi mật khẩu

~~~text
POST /me/change-password
  currentPassword, newPassword

Backend:
  1. Kiểm tra phiên, chính sách thay đổi và mức xác thực lại.
  2. Xác minh currentPassword hoặc bằng chứng thay thế được cho phép.
  3. Kiểm tra newPassword và tạo verifier mới.
  4. Ghi verifier, phiên bản credential và sự kiện kiểm toán.
  5. Thu hồi hoặc xem xét lại phiên/token theo chính sách.
  6. Thông báo thay đổi, không ghi dữ liệu mật khẩu vào log.
~~~

**Bài học từ ví dụ:** cùng một credential được sử dụng ở nhiều luồng nhưng **điều kiện ra quyết định** khác nhau. Việc đặt lại mật khẩu không được tái sử dụng endpoint đổi mật khẩu mà bỏ qua kiểm tra bằng chứng. Hơn nữa, mỗi API tài nguyên phải thực thi chính sách ở server; kiểm tra mật khẩu là một bước xác thực chứ không phải toàn bộ kiểm soát truy cập.

## 11. Các tình huống lỗi cần kiểm thử

| Tình huống kiểm thử | Hành vi mong đợi |
|---|---|
| Mật khẩu sai nhiều lần | Có kiểm soát lạm dụng; không cho thử vô hạn |
| Định danh không tồn tại | Không lộ dữ liệu tài khoản qua thông báo lỗi hoặc phản hồi quá khác biệt |
| Mật khẩu đúng nhưng tài khoản bị đình chỉ | Không cấp phiên đầy đủ |
| Tài khoản bắt buộc MFA nhưng chỉ nhập đúng mật khẩu | Chưa cấp quyền truy cập vào API bảo vệ |
| Mật khẩu dài có khoảng trắng/ký tự Unicode hợp lệ | Không bị cắt âm thầm; xử lý nhất quán |
| Mật khẩu nằm trong danh sách đã lộ | Bị từ chối theo chính sách ở bước tạo/đổi |
| Hai tài khoản chọn cùng mật khẩu | Salt/verifier lưu riêng, không trùng vì tái sử dụng salt |
| Token reset đã sử dụng được gửi lại | Từ chối, không đổi password lần nữa |
| Token reset đã hết hạn hoặc sai tài khoản | Từ chối |
| Reset mật khẩu cho tài khoản đã bị vô hiệu hóa | Tuân thủ điều kiện trạng thái, không tự kích hoạt lại |
| Đổi mật khẩu khi có phiên nghi bị chiếm quyền | Có xác thực lại và xử lý phiên/token theo chính sách rủi ro |
| Rò rỉ cơ sở dữ liệu verifier | Không có mật khẩu dạng rõ; KDF/salt gây khó khăn cho dò đoán ngoại tuyến |
| Client gửi \`passwordVerified=true\` | Server bỏ qua giá trị client tự tuyên bố và tự xác minh |
| Có JWT hợp lệ nhưng không có quyền với đối tượng | API từ chối truy cập theo phân quyền |

## 12. Bài tập phân tích tình huống

**Bối cảnh:** Một ứng dụng cho phép đăng ký bằng email và mật khẩu. Hệ thống lưu \`SHA256(password)\` trong cơ sở dữ liệu, không giới hạn thử sai; sau năm lần đăng nhập sai thì khóa tài khoản vĩnh viễn. Người dùng có thể nhấp “Quên mật khẩu”, nhận liên kết có hiệu lực ba ngày và sử dụng nhiều lần. Khi đặt lại, tất cả phiên cũ vẫn dùng được. Quản trị viên bắt buộc nhập OTP qua SMS.

**Yêu cầu:** Xác định các điểm yếu và đề xuất thay đổi theo từng ranh giới.

Gợi ý phân tích:

1. **Kho verifier:** SHA-256 trực tiếp quá nhanh cho mật khẩu con người. Dùng KDF chuyên dụng có salt riêng và tham số phù hợp; lên kế hoạch nâng cấp verifier cũ.
2. **Đăng nhập:** áp dụng điều tiết tốc độ, giám sát tấn công phân tán, MFA khi cần. Khóa vĩnh viễn sau vài lần sai có thể bị lợi dụng để gây từ chối dịch vụ.
3. **Khôi phục:** token cần ngẫu nhiên, đúng mục đích, ngắn hạn và chỉ dùng một lần; bảo vệ kênh phát hành, giới hạn số yêu cầu.
4. **Phiên sau reset:** có chiến lược thu hồi và rà soát các phiên, token, thiết bị, phương thức xác thực đã được thêm.
5. **Quản trị viên:** SMS OTP có thể cải thiện so với chỉ mật khẩu nhưng vẫn chịu phishing, chuyển SIM hoặc chặn tin nhắn; cân nhắc passkey/WebAuthn cùng quy trình khôi phục bảo đảm tương xứng.
6. **Tài nguyên:** ngay cả khi đăng nhập an toàn, API vẫn phải kiểm tra quyền ở cấp tài nguyên và hành động.

**Câu hỏi suy ngẫm:** Nếu chuyển toàn bộ tài khoản sang passkey nhưng vẫn cho phép đặt lại bằng email mà không có bảo vệ bổ sung, nguy cơ nào còn tồn tại? Hãy mô tả kịch bản chiếm tài khoản qua đường khôi phục và đề xuất cách bảo vệ đường này.

## 13. Checklist cho password credential

- [ ] Phân biệt identifier, password, verifier, phiên/token và quyền truy cập.
- [ ] Mật khẩu chỉ được nhận qua kênh bảo vệ; không đi vào URL, log hoặc công cụ phân tích.
- [ ] Server kiểm tra mật khẩu bằng thư viện chuyên dụng, không tin kết quả do client tự khai.
- [ ] Có chính sách độ dài phù hợp, chặn mật khẩu đã lộ, hỗ trợ trình quản lý mật khẩu và passphrase.
- [ ] Kho dữ liệu không lưu plaintext; sử dụng KDF chuyên dụng, salt riêng và tham số được đánh giá định kỳ.
- [ ] Quản lý pepper bên ngoài kho verifier nếu chọn triển khai, có phương án xoay vòng.
- [ ] Đăng nhập có giới hạn thử sai, giám sát credential stuffing/password spraying và giảm lộ tài khoản.
- [ ] Không cấp phiên đầy đủ trước MFA hoặc các điều kiện xác thực bắt buộc.
- [ ] Đổi mật khẩu và reset mật khẩu có quyền, bằng chứng và điều kiện trạng thái riêng.
- [ ] Token khôi phục dùng một lần, ngắn hạn, gắn đúng mục đích/tài khoản.
- [ ] Sau thay đổi do nghi bị lộ, có phương án xử lý phiên, token và các phương thức xác thực khác.
- [ ] Tài khoản bị vô hiệu hóa không thể được kích hoạt lại ngoài quy trình có thẩm quyền.
- [ ] API tiếp tục kiểm tra quyền trên từng tài nguyên, không suy ra quyền chỉ từ việc password đúng.
- [ ] Có kiểm thử cho mật khẩu dài, Unicode, tài khoản không tồn tại, thử sai phân tán và các tình huống replay.

## Ghi nhớ

Password credential là một **bằng chứng bí mật có thể bị biết và tái sử dụng**. Để sử dụng an toàn, cần ba lớp xuyên suốt vòng đời: **mật khẩu khó đoán và chưa bị lộ**, **verifier được bảo vệ bằng KDF chuyên dụng với salt**, và **quy trình xác minh/đổi/khôi phục chống lạm dụng**.

Mật khẩu không tự giải quyết phishing, đánh cắp phiên hay kiểm soát quyền truy cập. Thiết kế xác thực an toàn phải kết hợp MFA hoặc passkey khi thích hợp, bảo vệ phiên/token, quản lý trạng thái tài khoản và phân quyền tại dịch vụ tài nguyên.
