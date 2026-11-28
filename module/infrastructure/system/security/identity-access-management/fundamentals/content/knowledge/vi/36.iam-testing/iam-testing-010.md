# Federation assertion test

## 1. Kiểm thử assertion trong liên kết danh tính nhằm chứng minh điều gì?

**Federation assertion test** kiểm tra rằng ứng dụng chỉ chấp nhận bằng chứng danh tính từ một nguồn được tin, dành cho đúng bên nhận, trong đúng luồng và khi những điều kiện sử dụng vẫn còn hiệu lực.

Trong federation, ứng dụng không trực tiếp thực hiện mọi bước xác thực. Nó dựa vào một hệ thống khác để nhận thông tin về chủ thể và sự kiện xác thực. Vì vậy, điểm tiếp nhận phải kiểm chứng cả thông điệp và ngữ cảnh mà thông điệp được dùng.

Một assertion có chữ ký hợp lệ vẫn có thể không dành cho ứng dụng hiện tại, đã hết hạn, thuộc một request khác hoặc mang thuộc tính không được phép ánh xạ thành quyền cục bộ.

Mục tiêu kiểm thử là chứng minh toàn bộ ranh giới đó. Một ca “đăng nhập SSO thành công” chỉ xác nhận đường hợp lệ hoạt động; nó chưa chứng minh ứng dụng sẽ từ chối thông điệp sai bên nhận, sai ngữ cảnh hoặc bị sử dụng lại.

Assertion trong bài được hiểu là bằng chứng danh tính trong luồng federation. Các định dạng và profile khác nhau có quy tắc riêng; không áp dụng máy móc cùng một bộ field cho mọi giao thức.

## 2. Phân biệt SAML assertion và bằng chứng xác thực trong OIDC

Trong SAML, assertion chứa những thông tin mà bên phát hành xác nhận, cùng các điều kiện và phần bảo vệ liên quan theo profile. Trong OIDC, ID token mang thông tin về sự kiện xác thực và chủ thể cho client; luồng còn có những phần như request, phản hồi, đổi code và trạng thái giao dịch.

Hai cách tích hợp có mục tiêu liên quan nhưng không đồng nhất về định dạng hay cách kiểm chứng.

| Khía cạnh | SAML trong ngữ cảnh phù hợp | OIDC trong ngữ cảnh phù hợp |
|---|---|---|
| Nguồn phát hành | Issuer và cấu hình trust của IdP | Issuer và cấu hình trust của OpenID Provider |
| Chủ thể | Subject và định danh theo hợp đồng | Subject cùng ngữ cảnh issuer |
| Bên nhận và phạm vi sử dụng | Audience, recipient, destination hoặc điều kiện liên quan theo profile | Audience của ID token, client liên quan và các ràng buộc của flow |
| Thời gian | Điều kiện thời gian của assertion và xác nhận chủ thể nếu có | Thời hạn và các claim thời gian bắt buộc theo flow hoặc profile |
| Liên kết giao dịch | Request ID, InResponseTo và trạng thái theo luồng áp dụng | State, nonce và các ràng buộc của luồng tương ứng |
| Bảo vệ thông điệp | Chữ ký và mã hóa nếu profile hoặc hợp đồng yêu cầu | Kiểm chứng ID token và bảo vệ những bước của flow tương ứng |

Không nhận access token thay cho ID token ở một điểm đang cần bằng chứng xác thực cho client chỉ vì nó cũng có dạng JWT. Tương tự, một ID token không tự là access token cho API nghiệp vụ.

Các cơ chế state, nonce và liên kết request không thay thế chữ ký hoặc trust của nguồn phát hành. Chúng giải quyết những phần khác nhau của hợp đồng xác thực.

## 3. Viết hợp đồng chấp nhận trước khi dựng test

Kỳ vọng của test phải xuất phát từ một hợp đồng được xác định, gồm:

- Giao thức, flow, binding hoặc profile được ứng dụng hỗ trợ.
- Những issuer và tenant được phép kết nối tới client hoặc service provider tương ứng.
- Nguồn khóa, metadata, thuật toán và điều kiện bảo vệ thông điệp được chấp nhận.
- Bên nhận, callback hoặc endpoint đích đã cấu hình.
- Quy tắc thời gian, độ lệch đồng hồ và mức độ mới của xác thực khi cần.
- Cách liên kết request, browser transaction và phản hồi.
- Cách phát hiện replay hoặc xử lý callback lặp theo hợp đồng.
- Claim bắt buộc, ý nghĩa của claim và quy tắc liên kết tài khoản.
- Cách thất bại khi một phụ thuộc hoặc cấu hình cần thiết không có.

Ví dụ, hệ thống chỉ hỗ trợ luồng SAML do service provider khởi tạo sẽ có yêu cầu liên kết request khác với một cấu hình được phép nhận một số phản hồi do IdP khởi tạo. Không viết test bắt buộc mọi trường hợp đều có cùng một giá trị InResponseTo mà bỏ qua flow thực sự được hỗ trợ.

Ngược lại, nếu một đường chỉ được phép nhận phản hồi cho request đã khởi tạo, không được mở nhận phản hồi không có request chỉ để một fixture đăng nhập thành công.

Hợp đồng cũng cần chỉ rõ điều gì là bằng chứng danh tính và điều gì vẫn thuộc authorization cục bộ. Một IdP được tin để xác nhận nhân viên không mặc nhiên được cấp role quản trị ứng dụng qua bất kỳ claim nào nó gửi.

## 4. Dựng môi trường và fixture có thể kiểm soát

Dùng IdP hoặc bộ phát thông điệp kiểm thử, khóa thử nghiệm và tài khoản tổng hợp trong môi trường được phép. Không cần dùng credential hoặc hồ sơ production để đánh giá các điều kiện chấp nhận.

Một fixture nên có các thành phần sau:

| Thành phần | Mục đích |
|---|---|
| Issuer-A được tin cho ứng dụng | Tạo thông điệp hợp lệ và những biến thể được ký đúng để cô lập một điều kiện |
| Issuer-B không được ứng dụng chấp nhận | Kiểm tra ranh giới nguồn phát hành |
| Client hoặc service provider thứ hai | Tạo bằng chứng đúng chữ ký nhưng dành cho bên nhận khác |
| Khóa hiện tại, khóa dự kiến xoay và khóa không được tin | Kiểm tra cập nhật cấu hình và phạm vi trust |
| Hai chủ thể có định danh hoặc email dễ gây nhầm | Kiểm tra liên kết tài khoản theo nguồn và ngữ cảnh |
| Đồng hồ và trạng thái giao dịch kiểm soát được | Kiểm tra thời gian, correlation và replay một cách lặp lại được |

Test harness cần thể hiện rõ actor, issuer, client, tenant và request nào đang được sử dụng. Không để session quản trị còn tồn tại trong HTTP client làm kết quả đăng nhập bị hiểu sai.

Với test qua browser, cần quản lý cookie, state và phiên riêng cho từng ca. Với test callback, cần biết ca đó có đi qua bước tạo giao dịch thực tế hay đang chỉ kiểm thử một thành phần ở lớp thấp hơn.

## 5. Positive control và nguyên tắc thay đổi một điều kiện

Trước khi chạy biến thể bất hợp lệ, cần một baseline đi qua đúng luồng và tạo được danh tính cục bộ mong đợi.

Positive control nên xác nhận:

- Đúng issuer và subject được liên kết với đúng tài khoản cục bộ.
- Những thuộc tính được ánh xạ có giá trị và nguồn như kỳ vọng.
- Phiên được tạo theo đúng trạng thái của luồng.
- Quyền cục bộ không vượt mapping được phê duyệt.
- Dấu vết giao dịch đủ để phân biệt ca test với lần chạy khác.

Khi kiểm tra audience sai, không chỉ sửa byte audience trong một thông điệp đã ký rồi kết luận hệ thống kiểm tra audience tốt. Nếu chữ ký bị phá, request có thể bị từ chối trước khi điều kiện audience được đánh giá.

Để cô lập điều kiện đó, bộ phát kiểm thử có thể tạo một thông điệp mới có chữ ký hợp lệ trong trust đã thiết lập nhưng audience không đúng ứng dụng. Những điều kiện còn lại vẫn cần đáp ứng hợp đồng để ca test có ý nghĩa.

Tương tự, ca kiểm tra replay phải bắt đầu từ một thông điệp đã được chấp nhận hợp lệ lần đầu. Nếu nó luôn bị từ chối do sai chữ ký, test chưa chứng minh cơ chế replay hoạt động.

## 6. Kiểm thử nguồn, chữ ký và dữ liệu thực sự được sử dụng

### 6.1. Trust của nguồn phát hành

Cần có ca cho nguồn được tin, nguồn chưa đăng ký, nguồn đúng nhưng không được phép cho client hiện tại và những cấu hình nguồn có tên gần giống nhau.

Không để một issuer tự khai hoặc một khóa đính kèm chưa được tin tạo ra quan hệ trust mới. Nếu thông điệp có thông tin giúp tìm khóa, nó chỉ được dùng trong cơ chế và phạm vi cấu hình đã được quản trị.

Một issuer có thể được đọc để chọn trong tập cấu hình cho phép, nhưng chưa được dùng để cấp quyền trước khi những kiểm chứng cần thiết hoàn tất.

### 6.2. Chữ ký và thuật toán

Các ca có thể gồm chữ ký không hợp lệ, dữ liệu đã bị thay đổi, thiếu phần bảo vệ bắt buộc, khóa không được tin hoặc thuật toán ngoài tập được chấp nhận.

Với SAML, không mặc định mọi triển khai phải ký cả Response lẫn Assertion theo cùng một cách. Test phải bám profile và hợp đồng cụ thể, đồng thời chứng minh dữ liệu ứng dụng thực sự dùng nằm trong phần được bảo vệ đúng.

Một lỗi nguy hiểm là thư viện kiểm chứng một phần tử hợp lệ nhưng mã ứng dụng lại lấy danh tính từ một phần tử khác chưa được bảo vệ. Bộ test cần kiểm tra tính nhất quán giữa **nội dung đã được kiểm chứng** và **nội dung được dùng để tạo principal**.

Các thông điệp XML tổng hợp có cấu trúc mơ hồ, định danh phần tử trùng hoặc phần tử bổ sung không được phép có thể được dùng để kiểm chứng hành vi parser và thư viện trong phạm vi profile. Không tự viết bộ chọn phần tử thay cho cơ chế kiểm chứng giao thức đã được thiết kế phù hợp.

Parser cũng cần cấu hình an toàn đối với những tính năng XML không cần thiết. Ca kiểm chứng phải được cô lập, không làm phát sinh truy cập mạng hoặc tài nguyên ngoài môi trường thử nghiệm được phép.

### 6.3. Mã hóa không thay thế xác thực nguồn

Nếu hợp đồng yêu cầu assertion mã hóa, test cần xác nhận không chấp nhận bản không mã hóa hoặc không giải mã được theo điều kiện đã đặt. Nếu mã hóa không phải điều kiện của profile đang dùng, không tự coi thiếu mã hóa là lỗi cho mọi ca.

Một thông điệp giải mã được cũng chưa chứng minh nguồn phát hành hợp lệ. Điều kiện về chữ ký, issuer và ngữ cảnh vẫn phải được đánh giá theo hợp đồng.

## 7. Kiểm thử bên nhận, đích và điều kiện thời gian

### 7.1. Bên nhận đúng

Một thông điệp dành cho ứng dụng khác phải bị xử lý theo hợp đồng chấp nhận của ứng dụng hiện tại, dù nó đến từ cùng IdP và có chữ ký hợp lệ.

Trong SAML, cần kiểm tra những điều kiện về audience, recipient, destination và điểm tiếp nhận áp dụng cho profile. Không chỉ nhìn một trường rồi bỏ qua các trường hoặc quan hệ khác mà profile yêu cầu.

Trong OIDC, client kiểm tra audience và những điều kiện về client hoặc bên được ủy quyền theo flow, profile và cấu trúc token tương ứng. Không dùng một danh sách client chung rồi cho phép mọi token trong danh sách vào mọi ứng dụng.

Các cấu hình callback và bên nhận cần so khớp theo ngữ nghĩa được quy định. Một kiểm tra kiểu chuỗi chứa tên miền hoặc chấp nhận hậu tố tùy ý có thể làm phạm vi rộng hơn cấu hình đã duyệt.

### 7.2. Thời gian và mốc biên

Ca test cần bao gồm thông điệp còn hiệu lực, chưa đến thời gian được phép, đã hết hạn và các mốc sát biên theo độ phân giải của hệ thống.

Một assertion có thể có nhiều điều kiện thời gian với ý nghĩa khác nhau. Không xác nhận “chưa hết hạn” ở một trường rồi mặc định mọi điều kiện khác đều hợp lệ.

Độ lệch đồng hồ được chấp nhận phải có giới hạn. Test cần xác nhận cả phía trong và ngoài giới hạn, theo đúng ngữ nghĩa của từng field và profile, thay vì chỉ tăng độ lệch đến khi test pass.

Với yêu cầu xác thực gần đây, cần kiểm tra thông tin về thời điểm hoặc ngữ cảnh xác thực theo hợp đồng. Thời điểm phát hành token mới không tự chứng minh người dùng vừa thực hiện xác thực mạnh mới.

Nên điều khiển thời gian ở lớp kiểm thử phù hợp thay vì chờ nhiều phút bằng sleep. Với integration test, cần biết các thành phần nào sử dụng đồng hồ thật và những giới hạn đối chiếu liên quan.

## 8. Correlation giữa request, phản hồi và phiên browser

Thông điệp hợp lệ cho một giao dịch không được tự gắn vào một giao dịch khác chỉ vì cùng browser hoặc cùng email.

Với luồng SAML do service provider khởi tạo, các ca cần kiểm tra quan hệ giữa request đã phát, phản hồi và những điều kiện correlation theo profile. Có thể gồm request chưa tồn tại, request đã hoàn tất hoặc response gắn với giao dịch khác.

Với OIDC, kiểm tra state theo cơ chế của luồng, và nonce khi luồng hoặc request đã đặt yêu cầu tương ứng. State hỗ trợ liên kết phản hồi với giao dịch client; nonce có vai trò liên kết bằng chứng xác thực theo hợp đồng. Không dùng một cơ chế như sự thay thế hoàn toàn cho cơ chế còn lại.

Trong flow có authorization code, cần kiểm chứng các ràng buộc của bước đổi code, chẳng hạn client, callback và bằng chứng bổ sung khi được yêu cầu. Việc callback có một chuỗi code chưa đủ để tạo phiên trước khi luồng được hoàn tất đúng.

Một nhóm ca hữu ích gồm:

```text
Giao dịch X được khởi tạo ở browser context X
Giao dịch Y được khởi tạo ở browser context Y

Phản hồi hợp lệ cho X -> chỉ được xử lý trong ngữ cảnh phù hợp với X
Phản hồi của X gắn vào Y -> không tạo phiên sai ngữ cảnh
State hoặc nonce bắt buộc bị thiếu/sai -> không hoàn tất xác thực
Giao dịch đã hoàn tất -> callback lặp không tạo thêm quyền ngoài hợp đồng
```

RelayState hoặc những tham số điều hướng cũng cần xử lý theo hợp đồng của ứng dụng. Không tin một địa chỉ điều hướng do đầu vào cung cấp mà bỏ qua những giới hạn đã đặt chỉ vì assertion hợp lệ.

Không áp dụng yêu cầu của flow này lên một flow khác mà không phân biệt. Nếu IdP-initiated được hỗ trợ, nó cần bộ điều kiện và ca test riêng cho ranh giới chấp nhận của nó.

## 9. Replay và xử lý đồng thời

Replay là sử dụng lại một bằng chứng hoặc phản hồi trong bối cảnh mà nó không còn được chấp nhận. Thiết kế có thể dùng trạng thái giao dịch, định danh assertion hoặc các cơ chế của profile để kiểm soát việc sử dụng lại.

Một ca cơ bản:

1. Tạo một giao dịch và bằng chứng hợp lệ.
2. Gửi lần đầu, xác nhận kết quả thành công đúng chủ thể.
3. Gửi lại cùng bằng chứng theo kịch bản replay trong môi trường test.
4. Xác nhận không tạo thêm phiên, liên kết tài khoản hoặc quyền ngoài hành vi mà hợp đồng cho phép.

Một callback có thể được triển khai để xử lý lặp theo cách idempotent phù hợp. Khi đó cần kiểm tra chính hành vi đó, không mặc định mọi lần gửi lại đều phải có cùng một mã lỗi. Điều bất biến là không biến sự lặp lại thành một lần cấp thêm quyền hoặc một giao dịch danh tính khác ngoài hợp đồng.

Cần có ca đồng thời: hai request cùng tới trước khi trạng thái sử dụng được ghi nhận. Kiểm soát replay phải giữ đúng tính nguyên tử cần thiết, không chỉ hoạt động khi gửi tuần tự.

Trong hệ thống nhiều instance, thử các request ở những điểm tiếp nhận khác nhau thuộc môi trường kiểm thử. Một replay cache chỉ ở một node có thể không bảo vệ cùng bằng chứng khi nó đến node khác.

Thời gian giữ trạng thái replay phải phù hợp với khoảng thời gian bằng chứng còn có thể được chấp nhận, kể cả những giới hạn sai lệch đồng hồ áp dụng. Xóa trạng thái quá sớm có thể mở lại khả năng sử dụng một bằng chứng cũ còn trong cửa sổ chấp nhận.

## 10. Claim mapping và liên kết tài khoản

Ngay cả sau khi thông điệp được kiểm chứng, claim vẫn chỉ có ý nghĩa trong thẩm quyền và hợp đồng của issuer đó.

Cần kiểm tra những trường hợp:

- Thiếu thuộc tính bắt buộc hoặc kiểu dữ liệu không phù hợp.
- Cùng giá trị subject nhưng khác issuer.
- Email trùng giữa hai nguồn hoặc email đã thay đổi.
- Claim role hoặc group không có mapping được phê duyệt.
- Tenant được khai không phù hợp với cấu hình tích hợp hoặc tài khoản cục bộ.
- Mức xác thực không đủ cho chức năng yêu cầu.

Định danh cục bộ cần gắn với ngữ cảnh nguồn phù hợp. Không tự nối hai tài khoản chỉ vì tên hoặc email hiển thị giống nhau.

Một claim `admin` có chữ ký hợp lệ từ đối tác không mặc nhiên là quyền quản trị hệ thống nhận. Positive control nên kiểm tra mapping đúng; negative case cần chứng minh claim ngoài phạm vi không tạo role hoặc entitlement mới.

Nếu hệ thống tạo tài khoản ở lần đăng nhập đầu, cần test rằng một assertion không hợp lệ không để lại tài khoản, liên kết hoặc membership có thể sử dụng về sau. Nếu quy trình có bước tạo tạm theo thiết kế, trạng thái đó không được biến thành một tài khoản hoạt động trái hợp đồng.

Assertion hợp lệ cũng không chứng minh mọi quyền hiện tại vẫn còn. Trạng thái cục bộ và policy có thể yêu cầu kiểm tra thêm trước khi truy cập tài nguyên.

## 11. Ví dụ cấu trúc bộ test

Pseudocode dưới đây minh họa cách giữ các biến thể độc lập và kiểm tra tác động sau thất bại. Nó không phải triển khai SAML hoặc OIDC:

```text
contract = loadReviewedTestContract()

for case in federationCases:
    context = createIsolatedClientTransaction(case.flow)
    before = snapshotRelevantAccountAndSessionState()

    message = trustedTestIssuer.buildMessage(
        context,
        case.claims,
        case.conditions
    )

    message = applyTestVariationUsingCorrectProtection(message, case)
    result = submitThroughBoundaryUnderTest(context, message)

    if case.expected == ACCEPT:
        assertExpectedIssuerSubjectAndLocalAccount(result)
        assertExpectedSessionAndMappedPermissions(result)
    else:
        assertFailureMatchesReviewedContract(result, case)
        assertNoUnauthorizedSessionOrAccountLink(before)
        assertNoUnexpectedRoleOrCredentialCreated(before)

    assertExpectedSecurityEvidenceWithoutCredentialDisclosure(case)
    cleanupThisTestContext()
```

`applyTestVariationUsingCorrectProtection` nhấn mạnh rằng ca test cần thay đúng yếu tố muốn đánh giá. Một ca chữ ký sai sẽ cố ý phá bảo vệ; một ca audience sai có thể cần được IdP thử nghiệm ký lại hợp lệ để không bị che bởi lỗi chữ ký.

Kỳ vọng phải đến từ hợp đồng đã được xem xét, không gọi lại chính hàm xác thực của sản phẩm để tạo oracle. Bộ test cũng cần ghi rõ lớp nào đang được kiểm chứng, vì một unit test parser khác với một test hoàn tất login qua browser và tạo phiên thật trong môi trường thử nghiệm.

## 12. Xoay khóa, metadata và lỗi phụ thuộc

Federation phụ thuộc vào cấu hình trust và vòng đời khóa. Cần kiểm chứng cả thay đổi hợp lệ lẫn những trường hợp không thể lấy thông tin mới.

| Tình huống | Điều cần xác nhận |
|---|---|
| Khóa hiện tại hợp lệ | Thông điệp được xử lý đúng các điều kiện còn lại |
| Xoay sang khóa mới theo quy trình | Việc cập nhật trust và thời điểm chấp nhận đúng thiết kế |
| Khóa cũ còn trong giai đoạn được phép | Hành vi theo hợp đồng vòng đời, không tùy tiện chấp nhận mãi |
| Khóa đã bị thu hồi hoặc không còn được phép | Không dùng cache cũ để tiếp tục tin nguồn ngoài giới hạn |
| Key ID chưa biết hoặc metadata chưa tải được | Không bỏ kiểm chứng hoặc tin một nguồn tùy ý từ thông điệp |
| Dịch vụ trạng thái giao dịch hoặc replay lỗi | Không vô tình hoàn tất xác thực khi thiếu điều kiện cần thiết |

Một lỗi mạng không giống chữ ký không hợp lệ, nhưng cả hai đều không tự cho phép tạo danh tính nếu điều kiện bắt buộc chưa được đáp ứng. Nếu có phương án dùng cấu hình cục bộ, test phải kiểm tra chính giới hạn độ cũ và thời hạn của phương án đó.

Khi mô phỏng lỗi phụ thuộc, chỉ tác động các thành phần thuộc môi trường kiểm thử được phép. Cần kiểm tra cả giai đoạn phục hồi để một trạng thái replay, request cũ hoặc mapping lỗi không được khôi phục thành hợp lệ ngoài dự kiến.

## 13. Oracle, bằng chứng và cách tránh test pass giả

Một trang login hiện ra hoặc một mã HTTP lỗi không tự chứng minh assertion đã bị từ chối đúng nguyên nhân. Lỗi có thể đến từ route không tồn tại, cookie thiếu hoặc fixture chưa hoàn tất request ban đầu.

Cần đối chiếu kết quả với những bằng chứng thích hợp:

- Kết quả chấp nhận hoặc từ chối theo hợp đồng bên ngoài.
- Principal và tài khoản cục bộ thực sự được tạo hoặc sử dụng.
- Trạng thái phiên, giao dịch và replay liên quan.
- Role, membership, liên kết tài khoản hoặc credential phát sinh.
- Nhóm lý do trong audit nội bộ được phân quyền, nếu hệ thống có.

Thông điệp bị từ chối không được để lại một phiên hợp lệ qua một nhánh xử lý khác. Một trường hợp callback trả lỗi sau khi đã tạo liên kết đặc quyền vẫn là test fail về tác động, dù status code nhìn có vẻ đúng.

Không ghi assertion nguyên vẹn, ID token, authorization code, session cookie hoặc secret vào báo cáo. Dữ liệu thử nghiệm cũng có thể trở thành credential hợp lệ trong môi trường test và cần được bảo vệ.

Bằng chứng nên dùng mã ca, profile, issuer giả lập, nhóm điều kiện, phiên bản cấu hình và kết quả. Nếu cần giữ thông điệp để phân tích, phải có phạm vi, quyền truy cập và thời gian lưu phù hợp, thay vì đính kèm vào mọi log CI.

## 14. Ma trận coverage và tổ chức chạy kiểm thử

Một bộ test có thể truy vết tới các ranh giới sau:

| Ranh giới | Ca cần có |
|---|---|
| Nguồn phát hành | Nguồn đúng, nguồn không được tin và nguồn không được phép cho client này |
| Bảo vệ thông điệp | Chữ ký đúng, sai, bị sửa và thiếu bảo vệ bắt buộc |
| Nội dung được sử dụng | Principal được lấy từ đúng dữ liệu đã được kiểm chứng |
| Bên nhận | Thông điệp cho đúng ứng dụng và cho ứng dụng khác |
| Thời gian | Chưa hiệu lực, còn hiệu lực, hết hạn và các mốc biên có kiểm soát |
| Correlation | Đúng request, sai request, thiếu hoặc sai state/nonce khi bắt buộc |
| Replay | Lần đầu, gửi lặp, đồng thời và qua nhiều điểm tiếp nhận |
| Flow được hỗ trợ | SP-initiated, IdP-initiated hoặc flow OIDC theo cấu hình thực tế |
| Mapping | Thiếu claim, sai kiểu, role ngoài phạm vi và tenant không phù hợp |
| Liên kết danh tính | Cùng subject khác issuer, email trùng hoặc thay đổi |
| Vòng đời trust | Xoay khóa, thu hồi, metadata lỗi và cache quá cũ |
| Tác động sau thất bại | Không tạo phiên, liên kết hoặc quyền trái hợp đồng |

Unit test có thể kiểm tra nhanh những quy tắc và biến thể dữ liệu. Integration test cần chứng minh thư viện, cấu hình trust, kho giao dịch và cơ chế tạo principal phối hợp đúng. Một số ca end-to-end cần đi qua luồng thực tế để kiểm tra state, cookie, đổi code hoặc callback theo giao thức đang dùng.

Tách dữ liệu và trạng thái giữa các test song song, đặc biệt với request ID, nonce, session và replay cache. Một ca khác đã dùng cùng định danh có thể làm test từ chối mà không phản ánh điều kiện nó muốn đánh giá.

Khi báo cáo, ghi rõ profile, flow, phiên bản ứng dụng và cấu hình đã kiểm chứng. Kết quả pass ở một flow không tự bao phủ flow khác hoặc một cấu hình trust mới.

Federation assertion test có giá trị khi nó chứng minh ứng dụng chỉ tạo danh tính từ đúng bằng chứng trong đúng giao dịch và phạm vi tin cậy. Kiểm tra riêng bảo vệ thông điệp, điều kiện sử dụng, correlation, replay và tác động cục bộ giúp tránh việc một assertion nhìn có vẻ hợp lệ trở thành đường tạo phiên hoặc quyền ngoài dự kiến.
