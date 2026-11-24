# Localized recovery emails: bản địa hóa email khôi phục tài khoản

Email khôi phục tài khoản phải giúp người nhận hiểu vì sao họ nhận thư, thao tác nào được đề nghị và khi nào liên kết không còn dùng được. Nếu người dùng không hiểu ngôn ngữ của email, họ có thể bỏ qua yêu cầu hợp lệ, bấm nhầm liên kết hoặc cung cấp mã bí mật cho một người tự nhận là nhân viên hỗ trợ.

Trong SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY, **localized recovery emails** là các email khôi phục được điều chỉnh theo ngôn ngữ và quy ước trình bày phù hợp với người nhận. Nội dung có thể liên quan đến đặt lại mật khẩu, khôi phục MFA, hoặc bắt đầu một quy trình được phép khi mất passkey hay thiết bị xác thực.

Bản địa hóa cần làm rõ hướng dẫn, đồng thời giữ nguyên chính sách bảo mật. Một email tiếng Việt và một email tiếng Anh cho cùng loại sự kiện phải mô tả cùng một hành động, cùng giới hạn hiệu lực và cùng cách xử lý khi người nhận không yêu cầu khôi phục.

## 1. Email bản địa hóa gồm những phần nào?

Bản địa hóa không chỉ là dịch dòng tiêu đề. Người nhận có thể đọc thư qua danh sách email, thông báo trên điện thoại, bản HTML, bản văn bản thuần hoặc trình đọc màn hình.

| Thành phần | Điều cần thể hiện |
| --- | --- |
| Tên người gửi và tiêu đề | Nhận diện dịch vụ, mô tả đúng sự kiện, không chứa bí mật |
| Phần xem trước | Tóm tắt phù hợp, không để lộ token hoặc dữ liệu tài khoản không cần thiết |
| Nội dung chính | Vì sao nhận thư và hành động nào đang được đề nghị |
| Nút hoặc liên kết | Tên hành động rõ nghĩa, dẫn đến địa chỉ do hệ thống kiểm soát |
| Thời hạn | Giải thích đúng giới hạn sử dụng, tránh nhập nhằng múi giờ |
| Hướng dẫn khi không yêu cầu | Không dùng liên kết; truy cập ứng dụng theo cách quen thuộc để xem trợ giúp |
| Thông tin hỗ trợ | Kênh được cấu hình chính thức, không yêu cầu gửi mật khẩu hoặc mã |
| Bản văn bản thuần | Có cùng hướng dẫn và cùng đích khôi phục như bản HTML |

Một email “Xác nhận địa chỉ email”, một email “Đặt lại mật khẩu” và một email “Khôi phục phương thức xác thực” không nên dùng chung câu chữ chỉ vì cùng có một nút. Chúng thể hiện những hành động và rủi ro khác nhau.

Đặc biệt, không diễn đạt một liên kết bắt đầu xác minh thành “Nhấn để mở khóa toàn bộ tài khoản” nếu hệ thống còn yêu cầu các bằng chứng khác.

## 2. Chọn ngôn ngữ từ nguồn có kiểm soát

### 2.1. Phân biệt sở thích của chủ tài khoản và gợi ý của người gửi yêu cầu

Một yêu cầu khôi phục thường được gửi trước khi người yêu cầu đăng nhập. Vì vậy, ngôn ngữ trong request chưa chắc là ngôn ngữ chủ tài khoản muốn nhận email.

Ví dụ, tài khoản lưu ngôn ngữ tiếng Việt nhưng một người khác gửi yêu cầu với ngôn ngữ tiếng Anh. Nếu hệ thống lập tức ghi tiếng Anh vào hồ sơ, một yêu cầu chưa xác minh đã thay đổi tùy chọn của chủ tài khoản.

Có thể áp dụng chính sách như sau:

1. Ưu tiên ngôn ngữ thông báo đã lưu và được xác nhận trong hồ sơ.
2. Nếu chưa có, dùng gợi ý của luồng hiện tại khi sản phẩm cho phép.
3. Nếu gợi ý không hợp lệ hoặc không được hỗ trợ, dùng ngôn ngữ mặc định của dịch vụ.
4. Không lưu thay đổi ngôn ngữ vào hồ sơ chỉ từ thao tác khôi phục chưa xác minh.

Đây là một chính sách ví dụ. Một sản phẩm có thể cho người dùng chủ động chọn ngôn ngữ thư trong luồng, nhưng lựa chọn đó cần được giới hạn vào mục đích trình bày. Nó không cấp quyền thay đổi địa chỉ nhận, phương thức xác minh hay chính sách rủi ro.

Không suy ngôn ngữ chắc chắn từ địa chỉ IP, tên người dùng, quốc tịch hoặc đuôi miền email. Những tín hiệu này không đủ để xác định người nhận đọc được ngôn ngữ nào.

### 2.2. Danh sách ngôn ngữ được hỗ trợ

Ứng dụng nên ánh xạ đầu vào sang một danh sách hữu hạn, chẳng hạn:

```json
{
  "supportedLocales": ["vi", "en", "en-GB", "zh-Hans", "zh-Hant"],
  "defaultLocale": "en",
  "fallbacks": {
    "vi-VN": "vi",
    "en-AU": "en-GB"
  }
}
```

Cấu hình này chỉ minh họa quyết định của một sản phẩm; nó không phải bảng fallback chuẩn cho mọi hệ thống. Đặc biệt, không tự động gộp các hệ chữ khác nhau chỉ vì chúng có chung phần ngôn ngữ.

Dùng mã ngôn ngữ nhất quán để chọn catalog và đặt thuộc tính HTML. [W3C hướng dẫn khai báo ngôn ngữ HTML](https://www.w3.org/International/questions/qa-html-language-declarations.en) giải thích cách sử dụng thuộc tính `lang`, đồng thời phân biệt ngôn ngữ với hướng viết.

Không ghép trực tiếp giá trị locale từ request vào đường dẫn tệp, tên template hoặc tên lớp. Cần tra qua ánh xạ được kiểm soát; chuỗi như `../../template` không bao giờ trở thành địa chỉ tải mẫu.

## 3. Fallback phải giữ email hoàn chỉnh

Một email nửa tiếng Việt, nửa tiếng Anh có thể làm người dùng khó nhận ra hành động quan trọng. Nguy hiểm hơn là fallback từng chuỗi khiến tiêu đề nói “đặt lại mật khẩu”, còn nội dung hướng dẫn khôi phục MFA.

Với email khôi phục, có thể coi bộ sau là một đơn vị phiên bản:

```text
eventType
templateVersion
locale
subject
preview
plainText
html
requiredVariables
```

Nếu một bản dịch thiếu thành phần bắt buộc, chọn một bộ fallback hoàn chỉnh cho cùng loại sự kiện và cùng ngữ nghĩa bảo mật. Không gửi placeholder chưa thay, nội dung trống hoặc bản dịch đã cũ so với hành động thực tế.

Ví dụ:

| Tình trạng | Quyết định |
| --- | --- |
| Có bộ tiếng Việt hoàn chỉnh | Gửi toàn bộ thư bằng tiếng Việt |
| Chỉ thiếu phần xem trước tiếng Việt | Dùng bộ fallback hoàn chỉnh theo chính sách đã chọn |
| Thiếu nội dung tiếng Việt cho khôi phục MFA | Không lấy nhầm mẫu đặt lại mật khẩu tiếng Việt |
| Không có bộ nào tương thích với sự kiện | Không gửi thư sai nghĩa; xử lý lỗi vận hành và giữ phản hồi công khai phù hợp |
| Tên locale đầu vào không được hỗ trợ | Chọn fallback trước khi render |

Ngôn ngữ mặc định cũng là một phần của trải nghiệm cần được thiết kế. Nếu email dùng ngôn ngữ fallback, có thể cung cấp lựa chọn ngôn ngữ trên trang khôi phục mà không bắt người dùng đăng nhập trước.

Đổi ngôn ngữ hiển thị trên trang không được tạo quyền mới, kéo dài thời hạn hoặc tự làm token cũ hợp lệ trở lại.

## 4. Tách nội dung dịch khỏi dữ liệu bảo mật

### 4.1. Những giá trị không được dịch

Các thành phần sau cần giữ nguyên giá trị kỹ thuật:

- Token, mã dùng một lần và định danh giao dịch.
- Địa chỉ email nhận thư đã được xác định theo chính sách tài khoản.
- Đích khôi phục được cấu hình trên máy chủ.
- Thời điểm hết hạn và trạng thái token.
- Loại hành động mà token cho phép.

Có thể dịch câu “Liên kết chỉ dùng một lần”, nhưng không biến token sang chữ số địa phương, đổi chữ hoa thành chữ thường, thêm khoảng trắng hoặc chuẩn hóa Unicode tùy tiện.

Nếu mã có ký tự dễ nhầm, cách thiết kế mã cần được giải quyết ở cơ chế phát hành. Bản dịch không tự thay ký tự để làm mã “dễ đọc hơn”.

### 4.2. Một ngữ cảnh chung cho các định dạng

Ứng dụng có thể tạo một ngữ cảnh bất biến cho lần gửi:

```text
RecoveryMailContext
  eventType
  templateVersion
  locale
  registeredRecipient
  recoveryUrl
  issuedAt
  expiresAt
  expiryDescription
  officialSupportUrl
```

Bản HTML và bản văn bản thuần cùng dùng ngữ cảnh này. Không tạo token mới riêng cho mỗi định dạng, không tính thời hạn bằng hai công thức và không để người dịch tự sửa host.

Theo [OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html), liên kết khôi phục cần dùng HTTPS và được dựng từ miền tin cậy, tránh dựa vào Host header chưa được xác minh. Token cần có độ ngẫu nhiên phù hợp, giới hạn hiệu lực và bị vô hiệu hóa sau khi dùng. Bản địa hóa giữ nguyên các thuộc tính này.

Một URL minh họa có thể có dạng:

```text
https://accounts.example.com/recovery/continue?token=<opaque-token>&lang=vi
```

Đây là cấu trúc minh họa, không phải liên kết sử dụng thực tế. Nếu `lang` có thể chỉnh sửa, máy chủ chỉ dùng nó làm gợi ý hiển thị đã được kiểm tra. Quyền của token vẫn được xác định độc lập.

Không cho catalog bản dịch chứa một miền đích tùy ý. Một bản dịch có câu chữ chính xác vẫn có thể dẫn người dùng đến trang đánh cắp token nếu địa chỉ liên kết bị thay đổi.

### 4.3. Escape theo đúng ngữ cảnh

Thông điệp dịch và dữ liệu động không nên được nối thành HTML tùy ý.

- Dữ liệu đưa vào nội dung HTML cần được escape dưới dạng văn bản.
- Giá trị thuộc tính HTML cần được xử lý theo ngữ cảnh thuộc tính.
- Tham số URL cần được dựng bằng công cụ xử lý URL, sau đó URL hoàn chỉnh mới được đưa vào template.
- Tiêu đề thư cần đi qua thư viện email xử lý header; không nối giá trị không tin cậy chứa xuống dòng.

Escape HTML không kiểm tra một URL có thuộc miền được phép hay không. Kiểm tra đích và escape là hai bước riêng.

## 5. Viết câu chữ nhất quán giữa các ngôn ngữ

### 5.1. Dịch theo thông điệp hoàn chỉnh

Tránh ghép các mảnh như:

```text
"Liên kết" + "sẽ hết hạn sau" + minutes + "phút"
```

Thứ tự từ, số nhiều và cách đặt đơn vị có thể khác nhau giữa các ngôn ngữ. Catalog nên chứa thông điệp hoàn chỉnh với biến có tên rõ nghĩa.

Ví dụ minh họa:

```json
{
  "vi": {
    "subject": "Đặt lại mật khẩu cho tài khoản của bạn",
    "intro": "Chúng tôi đã nhận được yêu cầu đặt lại mật khẩu.",
    "action": "Tiếp tục đặt lại mật khẩu",
    "expiry": "Liên kết chỉ dùng một lần và hết hiệu lực vào {expiresAt}.",
    "unexpected": "Nếu bạn không gửi yêu cầu này, đừng sử dụng liên kết."
  },
  "en": {
    "subject": "Reset your account password",
    "intro": "We received a request to reset your password.",
    "action": "Continue password reset",
    "expiry": "This link can be used once and expires at {expiresAt}.",
    "unexpected": "If you did not request this, do not use the link."
  }
}
```

Catalog này chỉ thể hiện câu chữ. Nó không phải template engine và không tự bảo đảm việc thay biến, escape hay tạo URL an toàn.

Trong email khôi phục MFA, cần thay cả loại sự kiện và thông điệp tương ứng. Không chỉ thay chữ “mật khẩu” trong một câu rồi coi đó là quy trình tương đương.

### 5.2. Thời hạn và múi giờ

Ngôn ngữ không xác định múi giờ. Người đọc tiếng Việt có thể đang ở một quốc gia khác; một locale như `en` cũng không chỉ ra nơi họ đang sống.

Nếu hiển thị thời điểm tuyệt đối:

- Lấy giá trị từ `expiresAt` mà máy chủ đang thực thi.
- Chọn múi giờ từ nguồn được sản phẩm chấp nhận, hoặc hiển thị UTC rõ ràng.
- Viết ngày tháng và nhãn múi giờ đủ dễ hiểu.
- Tránh dạng ngày chỉ có số dễ bị đọc theo hai thứ tự khác nhau.

Ví dụ “Hết hiệu lực lúc 09:30 ngày 24 tháng 11 năm 2026 (UTC)” rõ hơn “Hết hạn 11/24 lúc 9:30”.

Nếu dùng câu tương đối như “còn khoảng 15 phút”, cần xác định đó là thời lượng tính từ lúc phát hành hay từ lúc dựng thư. Thời gian nằm trong hàng đợi và vận chuyển email có thể làm câu này không còn đúng khi người nhận mở thư.

Một lựa chọn là ghi thời điểm hết hiệu lực kèm múi giờ. Dù hiển thị theo cách nào, máy chủ vẫn quyết định token có còn hợp lệ tại lúc sử dụng hay không. Không tự kéo dài hạn vì thư gửi chậm.

### 5.3. Khi người nhận không yêu cầu

Hướng dẫn nên ngắn, bình tĩnh và có hành động phù hợp:

> Nếu bạn không gửi yêu cầu này, đừng sử dụng liên kết. Bạn có thể mở ứng dụng theo cách quen thuộc để xem hoạt động tài khoản và hướng dẫn bảo mật.

Không khẳng định mọi yêu cầu không mong đợi đều là tài khoản đã bị chiếm đoạt. Cũng không hứa rằng “chỉ cần bỏ qua là chắc chắn an toàn” cho mọi loại khôi phục.

Nếu quy trình còn có trạng thái chờ thay đổi phương thức xác thực, email cần mô tả chính xác trạng thái đó và cách phản hồi được sản phẩm cung cấp. Bản dịch không được tự thêm nút “hủy” mà hệ thống chưa hỗ trợ.

## 6. HTML và văn bản thuần phải tương đương

Một email HTML đẹp không bảo đảm người dùng sẽ đọc được. Ứng dụng email có thể chặn hình ảnh, thay cách trình bày hoặc chỉ hiển thị văn bản.

Có thể dùng `multipart/alternative` với bản văn bản thuần và bản HTML chứa cùng thông tin thiết yếu. [RFC 2046, mục 5.1.4](https://www.rfc-editor.org/rfc/rfc2046.html#section-5.1.4) mô tả các phần này là những cách biểu diễn thay thế của cùng dữ liệu; thông thường định dạng đơn giản đứng trước, định dạng phong phú hơn đứng sau.

Cần để thư viện email tạo MIME, charset UTF-8, boundary và mã hóa header phù hợp. Không tự ghép thư hoàn chỉnh bằng các dòng chuỗi lấy từ request.

### Mẫu nội dung văn bản thuần

```text
Đặt lại mật khẩu

Chúng tôi đã nhận được yêu cầu đặt lại mật khẩu cho tài khoản của bạn.

Để tiếp tục, mở liên kết:
{recoveryUrl}

Liên kết chỉ dùng một lần.
Hết hiệu lực: {expiresAtDisplay}

Nếu bạn không gửi yêu cầu này, đừng sử dụng liên kết.
Mở ứng dụng theo cách quen thuộc để xem hướng dẫn bảo mật.

Chúng tôi không yêu cầu bạn gửi mật khẩu hoặc mã xác thực qua email.
```

### Mẫu HTML tương ứng

```html
<!doctype html>
<html lang="vi" dir="ltr">
<head>
  <meta charset="utf-8">
  <title>Đặt lại mật khẩu</title>
</head>
<body>
  <h1>Đặt lại mật khẩu</h1>
  <p>
    Chúng tôi đã nhận được yêu cầu đặt lại mật khẩu
    cho tài khoản của bạn.
  </p>
  <p>
    <a href="{{ recoveryUrl }}">
      Tiếp tục đặt lại mật khẩu
    </a>
  </p>
  <p>Liên kết chỉ dùng một lần.</p>
  <p>Hết hiệu lực: {{ expiresAtDisplay }}</p>
  <p>
    Nếu bạn không gửi yêu cầu này, đừng sử dụng liên kết.
    Mở ứng dụng theo cách quen thuộc để xem hướng dẫn bảo mật.
  </p>
  <p>
    Chúng tôi không yêu cầu bạn gửi mật khẩu
    hoặc mã xác thực qua email.
  </p>
</body>
</html>
```

Các dấu `{{ ... }}` chỉ minh họa vị trí thay biến; template thực tế cần engine escape đúng ngữ cảnh. Không gửi nguyên dấu placeholder cho người nhận.

Nút HTML và URL trong bản văn bản thuần phải dẫn đến cùng giao dịch. Không để bản văn bản thuần trỏ về trang đăng nhập chung trong khi HTML có đường dẫn khôi phục cụ thể.

Token có thể cần nằm trong liên kết được gửi cho người nhận theo thiết kế của hệ thống. Tuy nhiên, không đưa nó vào tiêu đề, phần xem trước, tên ảnh hoặc tham số theo dõi. URL chứa token cũng không nên được ghi nguyên vào log.

## 7. Hướng viết, khả năng đọc và nhận diện dịch vụ

Với ngôn ngữ viết từ phải sang trái, cần xác định hướng viết phù hợp thay vì chỉ thay câu chữ. `lang` mô tả ngôn ngữ; `dir` mô tả hướng viết.

Trong một khối nội dung từ phải sang trái, mã dùng một lần, URL hoặc tên miền vẫn cần được trình bày để không bị đảo thứ tự về mặt thị giác. Có thể đặt nội dung kỹ thuật trong vùng có hướng phù hợp, nhưng không thay đổi giá trị gốc.

Ứng dụng email có mức hỗ trợ HTML và CSS khác nhau. Vì vậy, thông tin quan trọng cần giữ được ý nghĩa khi bố cục đơn giản hóa:

- Dùng văn bản thật cho hướng dẫn và tên hành động.
- Không đặt toàn bộ hướng dẫn trong ảnh.
- Giữ đoạn văn ngắn và liên kết có tên dễ hiểu.
- Không phụ thuộc vào màu sắc để phân biệt liên kết hết hạn hay còn hiệu lực.
- Tránh chữ viết tắt nội bộ mà người nhận không hiểu.
- Giữ tên thương hiệu và địa chỉ gửi nhất quán theo cấu hình chính thức.

Không yêu cầu người dùng tin thư chỉ vì email có logo hoặc viết đúng ngôn ngữ. Những đặc điểm đó cũng có thể bị giả mạo. Hướng dẫn nên giúp họ nhận ra hành động cụ thể và biết cách truy cập dịch vụ độc lập khi có nghi ngờ.

Nếu cá nhân hóa bằng tên hiển thị, coi tên là dữ liệu không tin cậy và chỉ đưa vào vị trí văn bản phù hợp. Lời chào trung tính thường đủ cho email khôi phục, đồng thời giảm thông tin tài khoản xuất hiện trên màn hình khóa.

## 8. Luồng tạo email trên máy chủ

Mã giả sau minh họa sự phân chia trách nhiệm. Nó không phải triển khai phát token hay gửi email hoàn chỉnh.

```text
handleRecoveryRequest(input):
    applyAbuseControls(input)

    account = findEligibleAccountInternally(input.identifier)
    publicResult = genericAcceptedResult()

    if account is not eligible:
        completeWithoutPublicAccountDisclosure()
        return publicResult

    locale = resolveSupportedLocale(
        savedPreference = account.notificationLocale,
        requestHint = input.locale,
        policy = recoveryLocalePolicy
    )

    bundle = selectCompleteBundle(
        eventType = input.allowedRecoveryEvent,
        locale = locale,
        version = configuredTemplateVersion
    )

    tokenRecord = issueRecoveryToken(
        account = account,
        purpose = input.allowedRecoveryEvent,
        policy = serverRecoveryPolicy
    )

    context = buildImmutableMailContext(
        recipient = account.registeredRecoveryAddress,
        tokenRecord = tokenRecord,
        bundle = bundle,
        trustedOrigin = configuredRecoveryOrigin
    )

    plainText = renderPlainText(bundle, context)
    html = renderHtmlWithEscaping(bundle, context)

    enqueueRecoveryMail(
        recipient = context.recipient,
        subject = bundle.subject,
        plainText = plainText,
        html = html,
        expiresAt = tokenRecord.expiresAt
    )

    return publicResult
```

`allowedRecoveryEvent` ở đây là giá trị đã được máy chủ cho phép, không phải một chuỗi tùy ý từ request. Tương tự, địa chỉ nhận lấy theo chính sách tài khoản, không lấy từ một trường “gửi đến email khác” chưa được xác minh.

Nhánh không có tài khoản không được trở thành một phản hồi nhanh có thể phân biệt dễ dàng với nhánh có tài khoản. Mã giả chưa triển khai điều phối thời gian, hàng đợi, chống lạm dụng hoặc xử lý lỗi; ứng dụng cần có cơ chế riêng cho các phần đó.

Trong thiết kế có hàng đợi, giữ phiên bản template và locale của lần gửi để retry không tự chuyển sang một loại thư khác. Thời hạn token không tự bắt đầu lại mỗi lần worker gửi email retry.

Không cần ghi token thô vào sự kiện quan sát. Có thể ghi mã giao dịch nội bộ, loại sự kiện, locale thực tế, phiên bản mẫu và kết quả gửi. Nếu hàng đợi bắt buộc mang dữ liệu chứa token, cần bảo vệ quyền truy cập, thời gian lưu và cơ chế che dữ liệu phù hợp với độ nhạy cảm đó.

## 9. Những sai lệch dễ gặp

| Sai lệch | Hệ quả | Quyết định thiết kế |
| --- | --- | --- |
| Lấy locale từ request rồi lưu ngay vào hồ sơ | Yêu cầu chưa xác minh thay đổi tùy chọn tài khoản | Chỉ dùng làm gợi ý trình bày theo chính sách |
| Fallback từng câu rời rạc | Trộn ngôn ngữ hoặc sai loại hành động | Chọn bộ thư hoàn chỉnh, tương thích sự kiện |
| Dịch cả mã hoặc token | Mã không còn khớp giá trị máy chủ | Chỉ dịch phần giải thích |
| Dựng miền từ Host header hoặc nội dung dịch | Liên kết có thể bị chuyển sang miền khác | Dùng origin tin cậy trên máy chủ |
| HTML và văn bản thuần có thời hạn khác nhau | Người nhận nhận hướng dẫn mâu thuẫn | Dùng chung ngữ cảnh và thời điểm hết hạn |
| Gửi lại thư làm phát hành token tùy tiện | Nhiều token hoặc thời hạn ngoài chính sách | Tách retry vận chuyển khỏi yêu cầu khôi phục mới |
| Chỉ có nút trong ảnh | Mất hành động khi ảnh bị chặn | Có liên kết bằng văn bản |
| Gắn theo dõi vào mọi liên kết | Token đi qua thêm hệ thống trung gian | Hạn chế theo dõi và viết lại liên kết nhạy cảm |

Phần mềm quét email có thể mở liên kết trước người dùng. Không nên để việc tải liên kết bằng GET tự hoàn tất thay đổi mật khẩu hoặc thay phương thức xác thực. Trang tiếp theo cần thực hiện hành động theo thiết kế giao dịch và điều kiện xác minh của hệ thống.

## 10. Tình huống áp dụng

Một tài khoản đã chọn tiếng Việt nhận yêu cầu đặt lại mật khẩu từ trình duyệt đang dùng tiếng Anh. Theo chính sách ưu tiên sở thích đã lưu, hệ thống gửi bộ email tiếng Việt cho địa chỉ khôi phục đã đăng ký.

Email nêu rõ đây là yêu cầu đặt lại mật khẩu, có một liên kết duy nhất cho giao dịch và thời điểm hết hiệu lực có nhãn múi giờ. Nếu bản dịch tiếng Việt của phiên bản mới chưa hoàn chỉnh, hệ thống dùng bộ fallback cho đúng sự kiện thay vì trộn chuỗi.

Người nhận có thể đổi ngôn ngữ trên trang khôi phục nếu cần. Thay đổi đó chỉ ảnh hưởng giao diện; token vẫn có cùng mục đích, cùng tài khoản, cùng thời hạn và cùng điều kiện sử dụng.

Nếu người nhận không gửi yêu cầu, email không thúc ép cung cấp bí mật cho nhân viên. Nó hướng dẫn không dùng liên kết và truy cập ứng dụng theo cách quen thuộc để xem trợ giúp.

Email khôi phục được bản địa hóa tốt giúp người dùng hiểu chính xác hành động đang diễn ra, trong khi dữ liệu xác minh và quyền của giao dịch vẫn được máy chủ kiểm soát nhất quán.
