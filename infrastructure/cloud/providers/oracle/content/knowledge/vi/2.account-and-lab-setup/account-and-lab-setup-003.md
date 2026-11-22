# Bảo vệ tài khoản quản trị ban đầu và bật MFA

## Mục tiêu và phạm vi

Tài khoản quản trị ban đầu của Oracle Cloud Infrastructure (OCI) có thể ảnh hưởng đến định danh, quyền truy cập và tài nguyên của cả tenancy. Trước khi tạo VCN, Compute, lưu trữ hoặc cơ sở dữ liệu cho lab, cần bảo vệ tài khoản này và kiểm tra rằng bạn vẫn có thể truy cập khi điện thoại hoặc phương thức xác thực chính gặp sự cố.

Bài thuộc chương **Tài khoản và môi trường thực hành** của module Oracle. Kết quả cần đạt gồm:

- Xác định đúng tài khoản, identity domain và đường đăng nhập đang sử dụng.
- Bảo vệ mật khẩu, email khôi phục và thiết bị xác thực.
- Đăng ký MFA, kiểm tra chính sách bắt buộc MFA và thử đăng nhập trong phiên mới.
- Chuẩn bị phương án khôi phục mà không tạo ngoại lệ bỏ MFA lâu dài.
- Tách tài khoản quản trị khỏi hoạt động lab thường ngày và các thông tin xác thực dùng cho tự động hóa.

Các đường dẫn thao tác được đối chiếu với tài liệu Oracle ngày **20/11/2026**. Giao diện có thể thay đổi theo loại tenancy và identity domain. Luồng chính trong bài dành cho **IAM with Identity Domains**; phần nhận diện môi trường giúp tránh áp dụng nhầm hướng dẫn dành cho mô hình cũ.

## 1. Vì sao phải bảo vệ tài khoản quản trị ngay từ đầu?

Trong tenancy có identity domains, Default identity domain chứa người dùng quản trị ban đầu và nhóm `Administrators`. Chính sách mặc định cho nhóm này quyền quản lý tài nguyên trong tenancy. Xem [The Default Identity Domain](https://docs.oracle.com/en-us/iaas/Content/Identity/domains/the_default_domain.htm).

Nếu thông tin đăng nhập bị chiếm đoạt, người truy cập trái phép có thể thực hiện thao tác theo quyền của tài khoản: thay đổi IAM, tác động đến dữ liệu hoặc tạo tài nguyên tiêu tốn chi phí. Vì vậy, bảo vệ tài khoản quản trị cũng góp phần bảo vệ ngân sách và khả năng khôi phục môi trường học tập.

Không dùng chung một tài khoản quản trị cho nhiều người. Mỗi người cần tài khoản riêng và quyền phù hợp với công việc. Với tài khoản cá nhân, có thể giữ tài khoản quản trị cho quản lý định danh, thanh toán và xử lý sự cố; tạo người dùng khác cho các bài lab khi đã học cách cấp quyền theo compartment.

### 1.1. Đăng nhập thành công khác với có quyền quản trị

Hai câu hỏi cần tách riêng:

- **Xác thực:** hệ thống có xác nhận đúng người đang đăng nhập không? Mật khẩu và MFA tham gia vào bước này.
- **Phân quyền:** người đó được làm gì sau khi đăng nhập? Nhóm, vai trò và IAM policy quyết định phạm vi thao tác.

Một người đăng nhập bằng MFA vẫn có thể thiếu quyền xem tài nguyên. Ngược lại, cấp thêm quyền quản trị không sửa lỗi OTP hoặc lỗi đăng nhập sai domain.

Vai trò quản trị identity domain cũng cần đọc đúng phạm vi. Đặc biệt, quyền quản trị một domain phụ không đồng nghĩa quyền quản trị toàn tenancy, như Oracle lưu ý tại [The Default Identity Domain](https://docs.oracle.com/en-us/iaas/Content/Identity/domains/the_default_domain.htm). Khi chuẩn bị người hỗ trợ khôi phục, kiểm tra quyền thực tế thay vì chỉ nhìn tên vai trò.

## 2. MFA bảo vệ điều gì?

**MFA (Multi-Factor Authentication)** yêu cầu nhiều yếu tố để xác minh danh tính. Trong luồng quen thuộc, người dùng nhập mật khẩu rồi cung cấp thêm mã hoặc xác nhận từ thiết bị đã đăng ký. Đây là lớp bảo vệ bổ sung khi chỉ mật khẩu bị lộ. Tham khảo [IAM MFA](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/iam_security_topic-IAM_MFA.htm).

Ví dụ:

```text
Mật khẩu tài khoản
        ↓
Yếu tố bổ sung từ thiết bị đã đăng ký
        ↓
Hoàn tất xác thực
        ↓
Quyền IAM quyết định thao tác được phép
```

Hai mật khẩu khác nhau vẫn cùng loại bí mật mà người dùng biết; không nên coi việc hỏi thêm một mật khẩu là tương đương sở hữu thêm một thiết bị xác thực.

### 2.1. Bật yếu tố, đăng ký yếu tố và bắt buộc MFA là ba việc khác nhau

| Việc cần kiểm tra | Ý nghĩa | Bằng chứng cần có |
| --- | --- | --- |
| Domain cho phép yếu tố | Quản trị viên bật phương thức mà người dùng có thể sử dụng | Yếu tố phù hợp xuất hiện trong cấu hình domain |
| Người dùng đã đăng ký | Tài khoản liên kết với ứng dụng hoặc thiết bị | Đăng ký hoàn tất và xác minh thành công |
| Chính sách yêu cầu MFA | Luồng đăng nhập vào ứng dụng buộc dùng thêm yếu tố | Phiên đăng nhập mới chịu chính sách đúng phạm vi |

Oracle phân biệt cấu hình của quản trị viên với đăng ký tự phục vụ của người dùng trong [Setting Up Account Recovery and 2-Step Verification](https://docs.oracle.com/en-us/iaas/Content/Identity/usersettings/manage_security_and_2_step_verification.htm). Vì vậy, thấy ứng dụng tạo được mã trên điện thoại chưa đủ chứng minh Console bắt buộc MFA cho tài khoản quản trị.

### 2.2. MFA cho Console có phạm vi riêng

Chính sách đăng nhập Console không tự bảo vệ mọi thông tin xác thực khác. Khóa riêng API, token của công cụ, khóa SSH và phiên trình duyệt cần được quản lý phù hợp với cách sử dụng của chúng. Chính sách MFA của OCI Console tác động đến đường đăng nhập Console theo [IAM MFA](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/iam_security_topic-IAM_MFA.htm).

Ví dụ, bật MFA không phải lý do để đưa khóa riêng API vào Git hoặc dùng tài khoản quản trị toàn tenancy cho mọi tác vụ tự động hóa. Khi học tự động hóa OCI, bạn sẽ cần cấp quyền đúng phạm vi và bảo vệ từng loại thông tin xác thực riêng.

## 3. Chuẩn bị trước khi đăng ký hoặc thay đổi chính sách

### 3.1. Xác định đúng tenancy, domain và đường đăng nhập

Ghi nhận tên tenancy, người dùng và identity domain của phiên hiện tại. Trong Console, tìm **Identity & Security → Domains**. Nếu có Domains, mở domain đang dùng rồi tìm phần **Security → Sign-on policies**. Nếu không có Domains, đối chiếu nhánh hướng dẫn dành cho tenancy không dùng identity domains. Xem [Determining the Tenancy Type](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/determining_the_tenancy_type.htm).

Đừng mặc định người dùng đang đăng nhập luôn nằm trong domain có tên `Default`, nhất là với tenancy đã chuyển đổi hoặc có nhiều domain. Hãy kiểm tra thông tin phiên đăng nhập và người dùng thực tế.

Nếu đăng nhập qua nhà cung cấp định danh bên ngoài như Microsoft Entra ID hoặc Okta, cần kiểm tra MFA tại IdP và luồng liên kết vào OCI. Không kết luận tài khoản được bảo vệ chỉ vì một người dùng cục bộ khác đã đăng ký MFA. Oracle phân biệt trường hợp dùng MFA tại IdP trong [IAM MFA](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/iam_security_topic-IAM_MFA.htm).

### 3.2. Bảo vệ mật khẩu và email khôi phục

Dùng mật khẩu riêng cho tài khoản quản trị, lưu trong trình quản lý mật khẩu và không chia sẻ qua chat, mã nguồn hoặc tài liệu lab. Bảo vệ cả hộp thư dùng để nhận thông báo và khôi phục tài khoản; một hộp thư dễ bị chiếm quyền sẽ làm yếu phương án khôi phục.

Trong **User settings → My profile → Security**, kiểm tra các phương thức khôi phục được domain cho phép. Có thể có email khôi phục, số điện thoại hoặc những lựa chọn khác theo cấu hình. Chọn thông tin mà bạn còn kiểm soát và hoàn tất xác minh nếu được yêu cầu. Tham khảo [Setting Account Recovery Options](https://docs.oracle.com/en-us/iaas/Content/Identity/usersettings/set-your-account-recovery-options.htm).

Không mặc định đặt lại mật khẩu sẽ khôi phục được yếu tố MFA đã mất. Hai việc này có thể cần những bước xử lý riêng.

### 3.3. Chuẩn bị thiết bị và đường khôi phục

Trước buổi thiết lập:

- Chuẩn bị điện thoại hoặc thiết bị xác thực tương thích, có khóa màn hình và còn quyền truy cập.
- Cài ứng dụng từ cửa hàng chính thức theo tài liệu Oracle; kiểm tra đúng nhà phát hành.
- Đồng bộ ngày giờ trên thiết bị nếu dùng mã theo thời gian.
- Chuẩn bị nơi lưu mã khôi phục tách khỏi chiếc điện thoại dùng xác thực chính.
- Biết ai có thể hỗ trợ quản trị domain hoặc cách liên hệ hỗ trợ chính thức khi mất truy cập.

Khi thay đổi chính sách cấp domain, giữ phiên quản trị hiện tại trong lúc thử phiên mới. Tuy nhiên, phiên cũ có thể hết hạn hoặc bị yêu cầu xác thực lại; nó không phải phương án khôi phục bảo đảm. Trước thay đổi ảnh hưởng mọi người dùng, phải có đường quản trị thay thế đã kiểm tra và hoàn tất các điều kiện chuẩn bị trong hướng dẫn Oracle.

## 4. Kiểm tra chính sách MFA cho OCI Console

Trong identity domain đang dùng, tìm policy **Security Policy for OCI Console**. Theo cấu hình dựng sẵn được Oracle mô tả, policy có hai rule: `MFA for administrators` được ưu tiên trước, tiếp đến `MFA for all users`. Cấu hình này yêu cầu đăng ký và cung cấp yếu tố bổ sung khi đăng nhập Console. Tham khảo [Identity Domains With the Security Policy for OCI Console Sign-On Policy](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/iam_security_topic-iam_mfa_identity_domains_signon_policy.htm).

Kiểm tra trạng thái active, ứng dụng Console được gán và rule thực tế đang áp dụng. Tên policy đúng nhưng bị vô hiệu hóa, bị thay đổi hoặc không bao phủ đúng người dùng chưa đủ để xác nhận hoàn thành.

Nếu policy dựng sẵn đang hoạt động đúng, tiếp tục đăng ký yếu tố và kiểm tra đăng nhập; không cần tạo thêm policy chỉ để có một policy mang tên riêng. Oracle khuyến nghị giữ cấu hình dựng sẵn theo best practice trong [hướng dẫn policy Console](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/iam_security_topic-iam_mfa_identity_domains_signon_policy.htm).

Với policy đã được rà soát nhưng chưa active, chức năng kích hoạt nằm tại trang chi tiết policy, **Actions → Activate sign-on policy**, sau đó xác nhận. Chỉ thực hiện sau khi hoàn tất chuẩn bị khôi phục và kiểm tra đúng phạm vi. Xem [Activating a Sign-On Policy](https://docs.oracle.com/en-us/iaas/Content/Identity/signonpolicies/activate-sign-policies.htm).

## 5. Đăng ký yếu tố xác thực cho tài khoản quản trị

### 5.1. Chọn phương thức được domain hỗ trợ

| Phương thức | Cách hoạt động | Điều cần chú ý khi thực hành |
| --- | --- | --- |
| Mobile app passcode | Ứng dụng tạo mã OTP; có thể tạo khi điện thoại không có mạng | Chọn đúng tài khoản trong ứng dụng, nhập mã còn hiệu lực |
| Mobile app notification | Ứng dụng nhận yêu cầu chấp thuận hoặc từ chối đăng nhập | Chỉ chấp thuận yêu cầu do bạn vừa khởi tạo |
| FIDO authenticator | Dùng thiết bị xác thực ngoài hoặc phương thức tích hợp được hỗ trợ | Kiểm tra tương thích và khả năng khôi phục trước khi dùng làm yếu tố chính |
| Bypass code | Dùng mã đã chuẩn bị để xác minh trong trường hợp cần thiết | Bảo vệ như bí mật xác thực, không dùng làm cách đăng nhập chia sẻ |

Oracle mô tả các yếu tố và việc hỗ trợ ứng dụng TOTP bên thứ ba tại [Configuring Authentication Factors](https://docs.oracle.com/en-us/iaas/Content/Identity/mfa/configure-authentication-factors.htm). Phương thức xuất hiện cho người dùng còn phụ thuộc cấu hình và loại domain. Không bật mọi yếu tố chỉ để có nhiều lựa chọn.

Luồng dưới dùng **Oracle Mobile Authenticator (OMA)**. OMA có thể tạo OTP hoặc nhận thông báo đăng nhập theo cách đã đăng ký; xem [Overview of the Oracle Mobile Authenticator App](https://docs.oracle.com/en-us/iaas/Content/Identity/mobileauthapp/use-oracle-mobile-authenticator-app.htm).

### 5.2. Đăng ký khi màn hình đăng nhập yêu cầu

Khi policy yêu cầu enrollment, làm theo màn hình **Enable Secure Verification** hoặc bước thiết lập xác minh tương ứng. Dùng ứng dụng phù hợp với phương thức đang được chọn, hoàn tất liên kết tài khoản và bước xác minh cuối cùng. Tài khoản chỉ nên được ghi nhận đã đăng ký khi Console xác nhận quy trình hoàn tất.

Không dừng ở thời điểm thấy một mục tài khoản xuất hiện trong ứng dụng. Có thể bạn mới thực hiện bước liên kết nhưng chưa hoàn tất xác minh trên trình duyệt.

### 5.3. Đăng ký từ My profile nếu chưa thực hiện

Nếu giao diện cho phép đăng ký tự phục vụ:

1. Mở **Profile → User settings**.
2. Trong **My profile**, chọn **Security**.
3. Tại **2-Step verification**, chọn **Enable** nếu chưa bật.
4. Chọn yếu tố được hỗ trợ, thực hiện các bước hiển thị.
5. Hoàn tất **Verify** để kết thúc kích hoạt.

Luồng này được mô tả trong [Activating 2-Step Verification](https://docs.oracle.com/en-us/iaas/Content/Identity/mfa/enroll-2-step-verification-first-login.htm).

Với OMA và mã QR, giao diện có thể hiển thị **Mobile app → Configure**. Mở OMA trên điện thoại, chọn **Add account**, quét mã QR đang hiển thị trên Console và hoàn tất xác minh. Tham khảo [Adding an Account to the OMA App by Scanning the QR Code](https://docs.oracle.com/en-us/iaas/Content/Identity/mobileauthapp/add-account-oma-app-scanning-qr-code.htm).

**Mã QR enrollment và khóa thiết lập thủ công là dữ liệu bí mật.** Không chụp vào tài liệu bài tập, không đưa lên Git và không chia sẻ màn hình chứa chúng. Nếu cần bằng chứng hoàn thành, dùng trạng thái đã đăng ký sau khi đóng phần hiển thị bí mật.

### 5.4. Thói quen sử dụng MFA đúng cách

Mã OTP không tự chống được mọi hình thức lừa đảo. Kẻ tấn công có thể lừa người dùng nhập mã vào trang giả rồi sử dụng trong thời gian mã còn hiệu lực. NIST nêu giới hạn này đối với OTP trong [SP 800-63B](https://pages.nist.gov/800-63-4/sp800-63b.html).

Vì vậy:

- Mở trang đăng nhập từ địa chỉ đã xác minh hoặc dấu trang đã lưu.
- Kiểm tra đúng trang và đúng tài khoản trước khi nhập mật khẩu hoặc OTP.
- Từ chối thông báo đăng nhập mà bạn không khởi tạo.
- Không đọc OTP hoặc bypass code cho người tự nhận là nhân viên hỗ trợ.
- Nếu có yêu cầu lạ liên tiếp, ghi thời điểm và kiểm tra tài khoản từ thiết bị tin cậy.

Cài MFA là một phần của bảo vệ truy cập; cách xử lý yêu cầu xác thực hằng ngày cũng quyết định hiệu quả của nó.

## 6. Chuẩn bị khôi phục mà vẫn giữ bảo vệ MFA

### 6.1. Tạo và lưu bypass code

Sau khi đăng ký 2-Step Verification, nếu domain cho phép bypass code:

1. Mở **Profile → User settings → Security**.
2. Tìm **Bypass codes**, chọn **Generate**.
3. Lưu mã vào nơi an toàn, có thể truy cập khi không còn điện thoại chính.
4. Đóng phần hiển thị mã sau khi đã lưu đúng nơi.

Mã này có thể dùng như yếu tố xác minh thay thế khi bạn không có thiết bị, theo [Generating a Bypass Code](https://docs.oracle.com/en-us/iaas/Content/Identity/usersettings/generate-bypass-code.htm).

Ghi nhận điều kiện hiệu lực và số lần sử dụng hiển thị trong luồng của bạn; không mặc định một mã có giá trị vĩnh viễn. Trong ghi chép lab, chỉ ghi **đã tạo và đã lưu**, không ghi chính mã đó.

Ví dụ, lưu duy nhất một ảnh mã khôi phục trong điện thoại dùng OMA không giải quyết được tình huống mất điện thoại. Mục tiêu của đường khôi phục là còn sử dụng được khi yếu tố chính không còn khả dụng.

### 6.2. Xác định người hoặc danh tính quản trị hỗ trợ

Nếu có quản trị viên khác, xác nhận người đó có quyền xử lý yếu tố xác thực trong đúng identity domain. Nếu thiết lập danh tính quản trị dự phòng cho tenancy cá nhân, cũng bảo vệ danh tính đó bằng MFA, kiểm tra đăng nhập và bảo quản phương thức khôi phục phù hợp.

Hai tài khoản cùng phụ thuộc duy nhất một chiếc điện thoại chưa tạo đường khôi phục độc lập khi điện thoại mất. Đồng thời, tài khoản dự phòng không nên trở thành tài khoản quản trị được chia sẻ cho mọi hoạt động lab.

Quản trị viên có quyền phù hợp có thể reset yếu tố xác thực của người dùng. Reset sẽ xóa các yếu tố đã đăng ký và yêu cầu người dùng đăng ký lại trong lần đăng nhập tiếp theo; xem [Resetting Authentication Factors for User Accounts](https://docs.oracle.com/en-us/iaas/Content/Identity/users/reset-authentication-factors-user-accounts.htm).

### 6.3. Không đồng nhất bypass code với bỏ MFA trong policy

Hai việc này có tác động khác nhau:

- Bypass code là một phương thức xác minh được hệ thống cho phép sử dụng trong điều kiện nhất định.
- Ngoại lệ bỏ MFA làm một người dùng hoặc nhóm có thể đăng nhập mà không qua yêu cầu yếu tố bổ sung.

Không tạo ngoại lệ lâu dài cho tài khoản quản trị chỉ vì lo mất điện thoại. Hãy chuẩn bị khôi phục và kiểm tra nó. Nếu tổ chức có quy trình truy cập khẩn cấp, quy trình đó cần xác định người chịu trách nhiệm, cách bảo quản, cách kiểm tra và thời điểm rà soát.

Mã khôi phục cũng không sửa được mọi loại lỗi. Tài khoản bị vô hiệu hóa, bị rule từ chối truy cập hoặc thiếu quyền IAM cần được xử lý theo nguyên nhân tương ứng.

## 7. Kiểm tra hiệu lực bằng một phiên đăng nhập mới

Giữ phiên hiện tại trong lúc kiểm tra, rồi mở một hồ sơ trình duyệt sạch hoặc cửa sổ riêng tư của Chrome/Edge để tránh dùng lại phiên SSO. Dùng trình duyệt được OCI hỗ trợ; nếu dùng Firefox, ưu tiên hồ sơ mới vì chế độ Private Browsing không được Oracle hỗ trợ mặc định, theo [hướng dẫn xử lý đăng nhập](https://docs.oracle.com/en-us/iaas/Content/GSG/Tasks/signinginIdentityDomain.htm). Tự nhập địa chỉ đăng nhập đã xác minh, chọn đúng tenancy, domain và người dùng.

Thực hiện kiểm tra theo các tiêu chí:

| Kiểm tra | Kết quả mong đợi |
| --- | --- |
| Đăng nhập đúng tài khoản quản trị | Luồng áp dụng đúng domain và đúng người dùng |
| Yếu tố chính | Mã hoặc thông báo xác thực hoạt động và Console chấp nhận |
| Yêu cầu MFA | Không thể kết luận hoàn thành chỉ từ một phiên cũ đang mở |
| Đường thay thế | Biết cách chọn phương thức thay thế được domain cho phép |
| Quyền quản trị | Sau đăng nhập vẫn có quyền cần thiết để quản lý môi trường |
| Tài liệu ghi nhận | Có thời điểm kiểm tra và kết quả; không có bí mật xác thực |

Khi cần phương thức thay thế, màn hình xác minh có thể cung cấp **Show alternative login methods**. Chọn phương thức đã đăng ký hoặc bypass code được cho phép; xem [Signing In to an Identity Domain Using an Alternative Login Method](https://docs.oracle.com/en-us/iaas/Content/Identity/usersettings/sign-in-identity-domain-alternative-login-method.htm).

Không cố tình nhập sai liên tục để thử bảo mật; có thể kích hoạt cơ chế khóa tài khoản. Khi kiểm tra một mã khôi phục làm tiêu hao lượt dùng, cập nhật lại vật liệu khôi phục theo chức năng và điều kiện thực tế.

Nếu phiên mới không hỏi MFA, kiểm tra trước khi thay đổi:

1. Có thực sự là phiên mới, hay trình duyệt còn SSO hoặc trạng thái thiết bị tin cậy?
2. Người dùng đang vào qua local sign-in hay IdP bên ngoài?
3. Policy có active và được gán cho ứng dụng Console không?
4. Rule nào đang khớp người dùng, có ngoại lệ hoặc thứ tự ưu tiên khác dự kiến không?
5. Tần suất yêu cầu yếu tố bổ sung có đúng mục tiêu không?

Một ảnh chụp dòng “MFA enabled” không thay thế được kết quả đăng nhập thực tế.

## 8. Trường hợp chưa có policy Console dựng sẵn

Đây là nhánh cấu hình cấp domain, cần thực hiện theo [Identity Domains Without the Security Policy for OCI Console Sign-On Policy](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/iam_security_topic-iam_mfa_with_identity_domains.htm):

1. Hoàn tất prerequisites của Oracle, gồm phương án quản trị khôi phục qua client application được cấp quyền phù hợp và lưu bypass code.
2. Trong **Security → MFA**, cho phép các yếu tố cần dùng và cấu hình chúng.
3. Tạo sign-on policy cùng rule yêu cầu yếu tố bổ sung; kiểm tra `Enrollment: Required` và tần suất `Every time` theo mục tiêu.
4. Kiểm tra nhóm/người dùng khớp rule và thứ tự đánh giá.
5. Gán ứng dụng **Console**, kích hoạt policy rồi kiểm tra phiên đăng nhập mới.

Rule chỉ dành cho quản trị viên có thể làm người dùng khác không đăng nhập được nếu không có rule phù hợp. Không triển khai bằng cách sao chép một rule rời mà bỏ qua toàn bộ hướng dẫn và đường khôi phục.

Client application có quyền quản trị là một thông tin xác thực đặc quyền cần quản lý riêng. Đường khôi phục này phải được thiết kế, bảo quản và kiểm tra trước khi thay đổi diện rộng; không coi một phiên trình duyệt còn mở là sự thay thế cho nó.

## 9. Đổi điện thoại, mất thiết bị và khôi phục truy cập

### 9.1. Khi chuẩn bị đổi điện thoại

Lên kế hoạch trước khi xóa thiết bị cũ. Kiểm tra tài khoản có đường xác minh thay thế và xác định quản trị viên có thể hỗ trợ. Việc sao chép dữ liệu điện thoại không chứng minh liên kết OMA của tài khoản đã hoạt động trên máy mới.

Oracle hướng dẫn việc đăng ký OMA trên thiết bị mới hoặc đăng ký lại thiết bị hiện có thông qua reset yếu tố bởi quản trị viên identity domain, rồi thực hiện enrollment lại. Xem [Registering New And Reregistering Existing Mobile Devices](https://docs.oracle.com/en-us/iaas/Content/Identity/mobileauthapp/registering_mobile_devices_with_oma.htm).

Sau khi đăng ký lại, thử một phiên đăng nhập mới và cập nhật ghi nhận về yếu tố cùng phương án khôi phục. Không kết thúc việc chuyển thiết bị chỉ vì ứng dụng đã được cài thành công.

### 9.2. Khi mất điện thoại hoặc đã xóa ứng dụng

Thực hiện theo đường còn khả dụng:

1. Nếu có yếu tố thay thế hoặc bypass code hợp lệ, dùng phương thức đó để xác minh.
2. Nếu cần reset, liên hệ quản trị viên có quyền trong đúng domain; xác minh danh tính trước khi yêu cầu xử lý.
3. Sau reset, đăng ký lại yếu tố, thử đăng nhập mới và rà soát phương án khôi phục.
4. Nếu không còn đường quản trị sử dụng được, liên hệ Oracle Cloud Support theo hướng dẫn chính thức.

Oracle có hướng dẫn Live Chat cho vấn đề đăng nhập và MFA của Free Tier khi chưa vào được Console tại [Troubleshooting Signing In to the Console — Contacting Support](https://docs.oracle.com/en-us/iaas/Content/GSG/Tasks/signinginIdentityDomain.htm). Kênh hỗ trợ sẽ yêu cầu xác minh chủ tài khoản; không mặc định được khôi phục ngay lập tức.

Reset yếu tố của một người dùng là thao tác nhạy cảm. Không xử lý chỉ dựa trên một tin nhắn tự nhận là chủ tài khoản, và không vô hiệu hóa MFA cho cả domain để giải quyết sự cố của một người.

### 9.3. Phân loại lỗi trước khi xử lý

| Hiện tượng | Điều cần kiểm tra |
| --- | --- |
| OTP bị từ chối | Đúng mục tài khoản trong ứng dụng, mã còn hiệu lực, đồng hồ thiết bị đồng bộ |
| Không nhận push | Kết nối mạng, quyền thông báo, yêu cầu chờ trong OMA; dùng yếu tố thay thế nếu đã có |
| Không thấy Security hoặc yếu tố mong muốn | Đúng domain và cấu hình tự phục vụ/MFA mà quản trị viên cho phép |
| Đăng nhập thành công nhưng thiếu quyền | Nhóm, vai trò và IAM policy; không reset MFA để sửa lỗi phân quyền |
| Không hỏi yếu tố bổ sung | Phiên SSO, thiết bị tin cậy, đường IdP, policy và rule khớp người dùng |
| Đã reset nhưng ứng dụng cũ vẫn tạo mã | Mã tạo được trên thiết bị không chứng minh liên kết phía máy chủ còn hợp lệ |
| Nhận yêu cầu xác nhận không do mình tạo | Từ chối yêu cầu, kiểm tra tài khoản và thông báo cho người quản lý phù hợp |

Oracle mô tả việc đồng bộ đồng hồ, kiểm tra thông báo đang chờ và chuyển sang passcode trong [Using the Oracle Mobile Authenticator](https://docs.oracle.com/en-us/iaas/Content/Identity/mfa/use-oracle-mobile-authenticator-app.htm).

## 10. Giảm việc dùng quyền quản trị trong lab hằng ngày

Sau khi bảo vệ và kiểm tra tài khoản quản trị, chuẩn bị người dùng lab với quyền theo nhu cầu. Một người chỉ cần tạo Compute trong compartment học tập không nên mặc định có toàn quyền tenancy để thuận tiện.

Phân công có thể được ghi như sau:

| Loại truy cập | Mục đích | Cách sử dụng đề xuất |
| --- | --- | --- |
| Quản trị tenancy | IAM, thiết lập nền tảng, thanh toán, xử lý sự cố | Chỉ dùng khi cần quyền tương ứng, có MFA và khôi phục đã kiểm tra |
| Người dùng lab | Thực hành dịch vụ trong phạm vi cho phép | Quyền theo bài học và compartment, danh tính riêng |
| Tự động hóa | Triển khai hoặc quản lý tác vụ đã xác định | Thông tin xác thực và quyền riêng theo môi trường |

Đây là mô hình tổ chức công việc; các IAM policy cụ thể được thiết kế ở bài cấp quyền. Không xóa quyền quản trị của danh tính đang dùng trước khi có đường quản trị thay thế đã xác minh. Việc giảm quyền phải giữ khả năng quản lý và khôi phục tenancy.

Cũng không tạo sẵn nhiều API key hoặc token đặc quyền chỉ để phòng một tình huống chưa xác định. Với mỗi thông tin xác thực được tạo, cần biết mục đích, nơi sử dụng, người quản lý và cách thu hồi.

## 11. Theo dõi sự kiện sau khi thiết lập

Khi có quyền phù hợp, xem báo cáo đăng nhập và audit của identity domain để đối chiếu thời điểm thử nghiệm. Các sự kiện hữu ích gồm đăng nhập thành công/thất bại, đăng ký yếu tố MFA, tạo bypass code và thay đổi sign-on policy. Báo cáo có thể cung cấp rule khớp cùng mức xác thực; xem [Audit Log Report](https://docs.oracle.com/en-us/iaas/Content/Identity/reports/audit-log.htm).

Dùng sự kiện làm bằng chứng bổ sung cho phép thử đăng nhập. Đối chiếu đúng người dùng, thời điểm và tài nguyên được bảo vệ; không suy diễn từ một sự kiện không thuộc phiên bạn đang kiểm tra.

Nếu nhận thông báo thay đổi mật khẩu, reset MFA hoặc tạo mã khôi phục ngoài dự kiến, kiểm tra từ địa chỉ Console đã xác minh. Ghi nhận thời điểm và sự kiện liên quan trước khi liên hệ người quản trị; không đính kèm QR, OTP hoặc bypass code vào yêu cầu hỗ trợ.

## 12. Thực hành và tiêu chí hoàn thành

### Bước 1 — Lập ghi nhận môi trường

Dùng biểu mẫu không chứa bí mật:

```text
Tên tenancy:
Identity domain thực tế:
Tên người dùng quản trị:
Đường đăng nhập: local / IdP bên ngoài
Policy áp dụng cho Console:
Trạng thái policy và phạm vi rule đã kiểm tra:
Yếu tố chính đã đăng ký:
Đường khôi phục đã chuẩn bị:
Thời điểm thử đăng nhập mới:
Kết quả xác thực và quyền cần thiết:
Người/kênh hỗ trợ khi mất truy cập:
```

Không điền mật khẩu, khóa QR, OTP, bypass code, khóa riêng hoặc session token vào biểu mẫu.

### Bước 2 — Hoàn tất đăng ký và khôi phục

Đăng ký yếu tố theo luồng phù hợp với domain. Tạo bypass code nếu được cho phép và lưu an toàn. Kiểm tra thông tin khôi phục, người hỗ trợ và phạm vi quyền cần để xử lý khi thiết bị xác thực chính không còn dùng được.

### Bước 3 — Kiểm tra phiên mới

Đăng nhập từ một phiên sạch trong trình duyệt được hỗ trợ, thực hiện yếu tố bổ sung và xác nhận còn quyền quản trị cần thiết. Nếu kiểm tra đường thay thế, ghi lại kết quả và cập nhật vật liệu khôi phục khi cần. Chỉ đóng phiên thiết lập khi đã xác minh đường đăng nhập mới hoạt động.

### Bước 4 — Ghi kết quả có thể kiểm chứng

Bài thực hành hoàn thành khi:

- Xác định đúng tenancy, identity domain, người dùng và nơi thực thi MFA.
- Tài khoản quản trị đã đăng ký yếu tố và thử xác minh thành công.
- Policy áp dụng đúng cho đường đăng nhập Console, không chỉ có trạng thái enrollment.
- Một phiên đăng nhập mới đã hoạt động với yêu cầu xác thực phù hợp.
- Có đường khôi phục và biết giới hạn của đường đó khi mất thiết bị hoặc policy cấu hình sai.
- Tài liệu kết quả không chứa bí mật xác thực; không còn ngoại lệ bỏ MFA ngoài dự kiến.
- Có kế hoạch dùng danh tính ít quyền hơn cho lab thường ngày.

Kết quả này giúp bạn tiếp tục xây dựng môi trường OCI có phân quyền và tự động hóa mà vẫn giữ được quyền kiểm soát tài khoản quản trị ban đầu.
