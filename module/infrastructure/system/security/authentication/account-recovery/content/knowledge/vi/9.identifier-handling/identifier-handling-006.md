# Identifier alias policy — Chính sách bí danh định danh trong khôi phục tài khoản

## 1. Vì sao bí danh ảnh hưởng đến an toàn khôi phục?

Một người có thể đăng nhập bằng tên người dùng, email chính, email phụ hoặc định danh do tổ chức cấp. Những giá trị cùng dẫn đến một tài khoản được gọi là **bí danh định danh** — identifier alias. Bí danh giúp người dùng tìm lại tài khoản khi họ nhớ một địa chỉ cũ hoặc tên đăng nhập khác, nhưng cũng tạo thêm đường dẫn tới luồng khôi phục.

Trong khôi phục tài khoản, ánh xạ sai bí danh có thể nghiêm trọng hơn lỗi tìm kiếm. Hệ thống có thể gửi liên kết đặt lại mật khẩu tới người mới sở hữu địa chỉ cũ, cho phép thêm MFA vào sai tài khoản hoặc hợp nhất nhầm hai danh tính. Vì vậy, chính sách bí danh phải quy định rõ giá trị nào được nhận diện, thuộc tài khoản nào, được dùng vào mục đích gì và còn hiệu lực đến khi nào.

Bài học này thuộc phần xử lý định danh của module khôi phục tài khoản an toàn. Trọng tâm là bảo vệ bước chọn tài khoản và kênh khôi phục khi người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Bí danh giúp xác định đối tượng cần xử lý; bản thân việc biết hoặc nhập một bí danh không phải bằng chứng sở hữu tài khoản.

Sau bài học, người học có thể thiết kế một chính sách bí danh có phạm vi rõ ràng, phân biệt chuẩn hóa với tạo bí danh, quản lý vòng đời liên kết và tránh phát quyền khôi phục qua ánh xạ cũ hoặc mơ hồ.

## 2. Tách tài khoản, bí danh và kênh nhận bằng chứng

Cần phân biệt ít nhất bốn khái niệm:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Định danh tài khoản nội bộ | Khóa ổn định đại diện cho một tài khoản | `principalId = p-781` |
| Bí danh dùng để tra cứu | Giá trị được chính sách cho phép ánh xạ về tài khoản | Tên đăng nhập `lan.nguyen` |
| Địa chỉ liên hệ | Nơi nhận thông báo hoặc giao tiếp | Email nhận hóa đơn |
| Kênh khôi phục đủ điều kiện | Kênh đã được đăng ký, xác minh và cho phép trong chính sách khôi phục | Email dự phòng có quyền nhận challenge |

Một địa chỉ email có thể giữ nhiều vai trò, nhưng các vai trò phải được cấp rõ ràng. Email nhận hóa đơn không tự trở thành tên đăng nhập. Email đăng nhập không tự có quyền nhận liên kết bỏ MFA. Việc xác minh một địa chỉ mới chỉ chứng minh quyền kiểm soát địa chỉ đó tại thời điểm xác minh, không chứng minh người kiểm soát nó là chủ của một tài khoản cũ.

Tên người dùng thường không có khả năng nhận thư. Khi người dùng nhập tên đó, hệ thống tìm `principalId` rồi chọn kênh đã đăng ký và đủ điều kiện của tài khoản. Hệ thống không được diễn giải chuỗi nhập vào thành đích gửi tùy ý.

Một nguyên tắc xuyên suốt là:

```text
Bí danh hợp lệ -> xác định tài khoản ứng viên
Bằng chứng được kiểm tra + chính sách -> quyết định quyền khôi phục
```

Hai bước này độc lập. Tìm được tài khoản không cấp quyền đổi mật khẩu, tắt MFA, thêm passkey, thay email hay thu hồi session.

## 3. Chuẩn hóa không đồng nghĩa với công nhận bí danh

**Chuẩn hóa** tạo khóa so sánh theo quy tắc đã được hệ thống chấp nhận. **Công nhận bí danh** là quyết định rằng một định danh được liên kết với một tài khoản cụ thể. Không nên biến mọi chuỗi trông giống nhau thành các bí danh tương đương.

Ví dụ, một sản phẩm có thể coi `Lan.Nguyen` và `lan.nguyen` là cùng tên đăng nhập nếu chính sách từ lúc đăng ký đã không phân biệt hoa thường. Điều đó không cho phép suy ra rằng mọi địa chỉ email có dấu chấm, dấu cộng hoặc ký tự giống nhau đều thuộc một người.

| Loại định danh | Quy tắc cần xác định | Suy diễn nguy hiểm |
| --- | --- | --- |
| Tên người dùng | Hoa thường, Unicode, tập ký tự, độ dài, namespace | Tự thay ký tự trông giống nhau rồi trỏ sang tài khoản khác |
| Email | Phân tích địa chỉ, xử lý miền và phần trước `@` theo chính sách hỗ trợ | Xóa mọi dấu chấm hoặc hậu tố sau dấu `+` với mọi nhà cung cấp |
| Số điện thoại | Quốc gia, định dạng lưu, phân biệt phần mở rộng nếu có | Coi chuỗi thiếu mã quốc gia là duy nhất trên toàn hệ thống |
| Danh tính liên kết | Cặp nhà phát hành và chủ thể ổn định được hệ thống tin cậy | Tự liên kết hai danh tính chỉ vì có cùng email hiển thị |

Phần miền email và phần trước `@` có quy tắc khác nhau. Không nên áp dụng một phép chuyển toàn bộ email sang chữ thường hoặc quy tắc riêng của một nhà cung cấp nếu hệ thống chưa xác định và kiểm soát ý nghĩa của phép biến đổi đó. Nếu sản phẩm đã có chính sách địa chỉ không phân biệt hoa thường, luồng khôi phục phải dùng cùng chính sách với đăng ký và đăng nhập, đồng thời xử lý các xung đột dữ liệu đã có.

Với Unicode, chuẩn hóa và phát hiện ký tự gây nhầm lẫn phục vụ những mục tiêu khác nhau. Hai tên nhìn giống nhau không có nghĩa là cùng một chủ thể. Có thể cảnh báo hoặc từ chối một tên mới theo chính sách chống giả mạo; không nên dùng độ giống về hình thức để chuyển hướng yêu cầu khôi phục.

Một thay đổi quy tắc chuẩn hóa là thay đổi ý nghĩa của khóa tra cứu. Trước khi áp dụng, cần đánh giá các bí danh đang tồn tại có bị gom thành cùng một khóa hay không. Khi có xung đột, không chọn ngẫu nhiên bản ghi đầu tiên và không tự hợp nhất tài khoản.

## 4. Mô hình dữ liệu và các bất biến của chính sách

Ví dụ sau mô tả một bản ghi bí danh. Các giá trị là dữ liệu minh họa, không phải cấu hình bắt buộc cho mọi sản phẩm.

```yaml
aliasId: a-204
principalId: p-781
realmId: workspace-vn
kind: EMAIL
lookupKey: lan@example.com
roles:
  - LOGIN
  - RECOVERY_DELIVERY
state: ACTIVE
verifiedAt: 2026-10-01T08:00:00Z
bindingVersion: 4
```

`realmId` biểu diễn phạm vi danh tính, chẳng hạn một tenant hoặc không gian tài khoản độc lập. `roles` cho biết mục đích được cấp; `state` cho biết hiệu lực; `verifiedAt` là thông tin xác minh, không phải cam kết rằng kênh chưa bao giờ bị chiếm quyền.

Một mô hình thực tế có thể tách bảng bí danh, bảng liên hệ và bảng phương thức khôi phục. Điều quan trọng là giữ những bất biến sau:

1. **Tra cứu phải xác định duy nhất trong đúng phạm vi.** Với vai trò dùng để tìm một tài khoản, khóa gồm namespace hoặc realm, loại định danh và giá trị chuẩn hóa phải dẫn tới tối đa một tài khoản đang có hiệu lực.
2. **Không mơ hồ về loại định danh.** Nếu chuỗi có thể là cả username lẫn email, giao diện hoặc chính sách tra cứu phải xác định ý nghĩa; không thử nhiều cách rồi chọn tài khoản đầu tiên tìm được.
3. **Bí danh không phải khóa gốc của giao dịch.** Sau khi giải quyết ánh xạ, giao dịch giữ `principalId` ổn định; không liên tục tra lại email để xác định tài khoản cần sửa.
4. **Quyền tra cứu và quyền nhận challenge là hai quyết định riêng.** Có vai trò `LOGIN` không mặc nhiên có `RECOVERY_DELIVERY`.
5. **Liên kết có phiên bản và vòng đời.** Thay chủ sở hữu, đổi trạng thái hoặc đổi quyền sử dụng phải làm thay đổi dữ liệu dùng để đánh giá hiệu lực.

Nếu sản phẩm cho phép nhiều thành viên gia đình dùng chung email liên hệ, email đó không thể đồng thời là khóa discovery duy nhất cho từng thành viên nếu không có thêm thông tin phân biệt được chính sách cho phép. Lựa chọn là không cấp vai trò tra cứu cho email dùng chung, yêu cầu một định danh khác hoặc thiết kế luồng chọn tài khoản sau bước xác minh phù hợp. Không trả danh sách tài khoản gia đình cho người chỉ nhập email.

Tương tự, nếu cùng username được phép ở nhiều tenant, cần có ngữ cảnh tenant đáng tin cậy trong luồng xử lý. Không cho người dùng sửa tenant ở bước cuối để chuyển một challenge sang tài khoản cùng tên trong tổ chức khác.

## 5. Vòng đời bí danh: thêm, sử dụng, thu hồi và chuyển giao

### 5.1. Thêm bí danh vào tài khoản đã có

Một luồng thêm email làm bí danh khôi phục có thể gồm:

1. Người dùng xác thực vào đúng tài khoản; hành động nhạy cảm yêu cầu xác thực lại hoặc bằng chứng bổ sung theo rủi ro.
2. Máy chủ tạo yêu cầu thêm bí danh, gắn với `principalId`, loại, phạm vi và mục đích cụ thể.
3. Hệ thống gửi bằng chứng xác minh tới địa chỉ đề xuất. Bản ghi đang chờ chưa được dùng để khôi phục tài khoản.
4. Khi nhận bằng chứng hợp lệ, máy chủ kiểm tra thời hạn, tính dùng một lần, quyền của giao dịch và tình trạng tranh chấp khóa bí danh.
5. Trong một giao dịch nguyên tử, hệ thống kích hoạt liên kết đủ điều kiện, cập nhật phiên bản và ghi nhận sự kiện bảo mật.
6. Thông báo thay đổi được gửi qua các kênh an toàn phù hợp; trường hợp rủi ro cao có thể cần thời gian chờ hoặc quy trình xem xét.

Việc xác minh địa chỉ đề xuất không thay cho bước xác thực chủ tài khoản ở bước đầu. Nếu ai cũng có thể nhập `principalId` của nạn nhân rồi xác minh email của chính mình để thêm bí danh, hệ thống đã cho phép chiếm quyền tài khoản.

Cũng không được tự thêm bí danh chỉ vì người dùng đang khôi phục và nói rằng “địa chỉ cũ không dùng được nữa”. Mất tất cả kênh cần một quy trình xác minh riêng; địa chỉ mới có thể dùng để liên lạc trong hồ sơ hỗ trợ nhưng chưa đủ để cấp quyền trên tài khoản cũ.

### 5.2. Trạng thái phải có ý nghĩa rõ

| Trạng thái minh họa | Được dùng để tìm tài khoản? | Được dùng để gửi challenge? |
| --- | --- | --- |
| `PENDING` | Không | Chỉ nhận bằng chứng xác minh việc thêm bí danh, không nhận quyền khôi phục |
| `ACTIVE` | Theo vai trò đã cấp | Chỉ khi có vai trò khôi phục và còn đáp ứng chính sách |
| `SUSPENDED` | Không dùng để phát quyền; xử lý theo chính sách riêng | Không |
| `REVOKED` hoặc `RETIRED` | Không dùng như bí danh hoạt động | Không |

Đây là ví dụ phân loại. Sản phẩm phải xác định chính xác các trạng thái của mình và áp dụng đồng nhất ở API, tác vụ nền, bộ nhớ đệm và công cụ hỗ trợ.

Một alias bị đình chỉ do nghi ngờ xâm nhập không nên tiếp tục nhận reset link chỉ vì nó vẫn còn trong bảng liên hệ. Truy vấn phải kiểm tra cả vai trò, trạng thái, phạm vi và điều kiện rủi ro, thay vì chỉ tìm một email bất kỳ của tài khoản.

### 5.3. Thu hồi và tái sử dụng

Khi người dùng bỏ email cũ hoặc số điện thoại cũ, hệ thống cần ngừng sử dụng liên kết đó theo chính sách. Địa chỉ hoặc số điện thoại có thể được cấp lại cho người khác; việc người mới nhận được OTP hôm nay không chứng minh họ sở hữu lịch sử của tài khoản trước đây.

Có thể dùng thời gian cách ly, lưu dấu bí danh đã nghỉ hoặc cấm tái cấp một số loại định danh. Những lựa chọn này phụ thuộc sản phẩm, quyền riêng tư và chính sách lưu giữ; không có một khoảng thời gian cố định phù hợp cho mọi trường hợp. Dữ liệu lịch sử cần quyền truy cập và thời hạn lưu rõ ràng.

Nếu cho phép tái sử dụng bí danh cho tài khoản khác, cần xử lý đó như một liên kết mới. Không giữ quyền khôi phục của chủ cũ, không chuyển dữ liệu tài khoản và không cho giao dịch cũ tự chạy trên chủ mới.

## 6. Tra cứu và cấp quyền khôi phục qua bí danh

Một quy trình an toàn cần tách ba quyết định: phân tích định danh, giải quyết ánh xạ, rồi đánh giá chính sách khôi phục.

```text
discover(input, trustedRealm):
    key = parseAndCanonicalize(input, declaredIdentifierKind)
    alias = resolveUniqueActiveAlias(trustedRealm, key)

    if alias is absent or ambiguous:
        finishWithoutGrant()
        return genericDiscoveryResponse()

    account = loadByPrincipalId(alias.principalId)
    plan = evaluateRecoveryPolicy(account, alias)

    if plan permits a challenge:
        destination = selectPreviouslyRegisteredEligibleChannel(account, plan)
        createAndDeliverChallenge(account.principalId, destination, plan)

    return genericDiscoveryResponse()
```

Đây là mã giả mô tả các quyết định, không phải mã triển khai đầy đủ. Phần phản hồi công khai còn cần xử lý bất đồng bộ, giới hạn tần suất và giảm khác biệt thời gian. Không nên để từng nhánh mã giả trở thành một phản hồi HTTP khác nhau.

Các trường hợp không tồn tại, chưa xác minh, đã thu hồi, không đủ điều kiện hoặc mơ hồ đều không được tạo quyền khôi phục. Màn hình có thể dùng thông điệp có điều kiện: “Nếu thông tin khớp với tài khoản đủ điều kiện, hướng dẫn khôi phục sẽ được gửi qua kênh đã đăng ký.” Không tiết lộ bí danh nào là email chính hoặc tài khoản có bao nhiêu phương thức xác thực.

Đích nhận challenge phải lấy từ bản ghi đã đăng ký và được phép. Ví dụ, người dùng nhập username rồi thêm trường `sendTo = new-address@example.net` không thể khiến liên kết reset được gửi tới địa chỉ mới đó. Nếu cho chọn giữa nhiều kênh, việc hiển thị lựa chọn và kiểm tra quyền chọn kênh cần tuân theo mức bằng chứng đã đạt được.

Một token khôi phục nên được gắn với tài khoản nội bộ và mục đích cụ thể, cùng các ràng buộc hiệu lực cần thiết:

```text
challenge:
    principalId
    purpose
    recoveryTransactionId
    expiresAt
    consumedAt
    deliveryChannelId
    relevantBindingVersion
    relevantSecurityVersion
```

Cấu trúc này minh họa trạng thái phía máy chủ; không yêu cầu đưa các trường vào token công khai. Nếu token là chuỗi ngẫu nhiên, máy chủ có thể dùng giá trị băm của token để tìm bản ghi tương ứng. Token phải có tính khó đoán, thời hạn và cơ chế tiêu thụ một lần; alias không thay thế các yêu cầu đó.

Khi hoàn tất, hệ thống dùng `principalId` đã gắn trong giao dịch. Không lấy trường email do client gửi ở bước cuối để quyết định tài khoản được đổi mật khẩu. Những thay đổi liên quan đến liên kết hoặc trạng thái bảo mật phải được đánh giá lại theo chính sách trước khi thực hiện hành động được cấp quyền.

## 7. Xử lý tranh chấp, bộ nhớ đệm và thay đổi đồng thời

### Hai yêu cầu cùng nhận một bí danh

Hai giao dịch có thể cùng kiểm tra “bí danh chưa tồn tại”, cùng xác minh và cùng cố kích hoạt. Chỉ kiểm tra trong mã ứng dụng là chưa đủ. Cần ràng buộc duy nhất phù hợp tại nơi lưu trữ cho khóa tra cứu đang được cấp, kết hợp giao dịch nguyên tử ở bước xác nhận.

Nếu cho nhiều yêu cầu chờ cùng một giá trị, phải quy định rõ cách giải quyết lúc kích hoạt. Một yêu cầu đang chờ không nên giữ chỗ vô hạn để người ngoài ngăn người khác sử dụng địa chỉ của họ. Khi tranh chấp, không âm thầm chuyển bí danh khỏi tài khoản hiện hữu chỉ vì một yêu cầu mới cũng xác minh được địa chỉ.

### Token còn sống sau khi bí danh đã thay đổi

Giả sử challenge được tạo khi `a-204` thuộc `p-781`, sau đó bí danh bị thu hồi. Nếu token chỉ lưu email và cuối cùng tra email lại, nó có thể trỏ tới một chủ sở hữu khác. Việc gắn token với `principalId` loại bỏ chuyển hướng này, nhưng chưa đủ nếu kênh cũ đã bị đánh dấu không an toàn.

Cần kiểm tra trạng thái và các phiên bản liên quan. Chính sách có thể vô hiệu hóa challenge gắn với kênh bị thu hồi, hoặc vô hiệu hóa rộng hơn khi phát hiện sự cố tài khoản. Một thay đổi chỉ về tên hiển thị có thể không cần hủy mọi challenge; thay đổi vai trò khôi phục hoặc chủ sở hữu liên kết là thay đổi có ý nghĩa bảo mật.

Kiểm tra cuối cùng, tiêu thụ token và thay đổi thông tin xác thực cần được phối hợp nguyên tử ở phạm vi dữ liệu liên quan. Nếu kiểm tra phiên bản rồi cho phép một thao tác đồng thời thay đổi liên kết trước khi ghi kết quả, hệ thống vẫn có thể thực hiện quyết định dựa trên dữ liệu cũ.

### Cache và công việc gửi chậm

Cache cần được vô hiệu hóa hoặc kiểm tra phiên bản khi bí danh đổi trạng thái. Thời gian sống ngắn giúp giảm cửa sổ dữ liệu cũ nhưng không bảo đảm tính đúng của thao tác nhạy cảm. Đường cấp quyền phải kiểm tra nguồn trạng thái đủ mới hoặc một cơ chế nhất quán tương đương.

Tác vụ gửi chạy chậm cũng cần xem xét liên kết đã thay đổi hay chưa trước khi gửi. Payload cũ không nên tiếp tục gửi bí mật tới địa chỉ đã bị thu hồi. Nếu thư đã rời hệ thống và không thể thu hồi, việc hủy hiệu lực challenge phía máy chủ vẫn phải ngăn thư cũ cấp quyền ngoài chính sách.

## 8. Ví dụ: email cũ được chuyển cho người khác

Lan có tài khoản `p-781`, username `lan.nguyen`, email cũ `lan.old@example.com` và email khôi phục mới đã được xác minh. Lan thu hồi email cũ khỏi vai trò khôi phục. Sau một thời gian, địa chỉ cũ được nhà cung cấp hoặc tổ chức cấp cho Minh.

Minh có thể chứng minh mình nhận được thư tại địa chỉ cũ. Bằng chứng đó liên quan đến quyền kiểm soát hiện tại của địa chỉ, không cho Minh quyền đặt lại mật khẩu tài khoản `p-781`.

| Tình huống | Hành vi mong đợi |
| --- | --- |
| Minh nhập email cũ khi liên kết đã thu hồi | Không phát challenge cho tài khoản Lan qua liên kết đó; phản hồi công khai vẫn chung |
| Lan nhập username đang hoạt động | Hệ thống tìm đúng `p-781`, rồi chọn kênh đủ điều kiện theo chính sách hiện tại |
| Minh đăng ký tài khoản mới bằng email cũ, nếu chính sách cho phép | Tạo liên kết mới cho tài khoản mới; không kế thừa MFA, passkey, dữ liệu hoặc phiên của Lan |
| Một token cũ được dùng sau khi kênh của Lan bị thu hồi | Kiểm tra phạm vi, phiên bản và hiệu lực; không giải quyết lại email sang tài khoản Minh |
| Lan mất cả MFA lẫn email mới | Chuyển sang quy trình xác minh được phép; không tự chấp nhận email cũ chỉ vì nó xuất hiện trong lịch sử |

Giả sử Minh gửi yêu cầu “gộp tài khoản vì tôi sở hữu email này”. Bộ phận hỗ trợ không được coi trùng địa chỉ là đủ bằng chứng cho cả hai tài khoản. Gộp tài khoản hoặc chuyển bí danh là một nghiệp vụ riêng cần quyền, bằng chứng và kiểm soát xung đột rõ ràng.

Nếu hệ thống không nhận biết được việc địa chỉ bên ngoài đã đổi người sở hữu trong khi liên kết cũ vẫn còn hoạt động, nó không thể chỉ dựa vào một OTP để phân biệt Lan với Minh. Đây là rủi ro của kênh tái cấp, cần được cân nhắc khi cho phép email hoặc số điện thoại làm bằng chứng duy nhất, nhất là với hành động có hậu quả lớn như thay MFA.

Với đăng nhập liên kết, một nhà cung cấp đổi email của người dùng cũng không tự tạo danh tính mới. Ánh xạ nên dựa trên định danh chủ thể ổn định trong phạm vi nhà phát hành được tin cậy. Ngược lại, hai nhà phát hành trả cùng email không có nghĩa là hai tài khoản được tự động gộp.

## 9. Chống lạm dụng và bảo vệ thông tin bí danh

Một tài khoản có nhiều bí danh không nên được hưởng nhiều lần ngân sách gửi hoặc nhiều lượt đoán mã chỉ vì người tấn công đổi đầu vào. Cần phối hợp hạn mức theo nguồn truy cập, khóa định danh đã chuẩn hóa, tài khoản nội bộ sau tra cứu và giao dịch khôi phục.

Hạn mức theo tài khoản được dùng nội bộ để gộp các bí danh về cùng chủ thể. Không trả bộ đếm hoặc thời gian chờ riêng làm lộ rằng hai email thuộc cùng một tài khoản. Ở cửa tiếp nhận, quy tắc công khai phải áp dụng nhất quán cho định danh tồn tại và không tồn tại; quyết định có gửi thêm hay không có thể được giữ trong xử lý nội bộ.

Hai bí danh email cùng chuyển thư về một hộp thư cũng không phải hai bằng chứng độc lập. Không coi việc nhập hai OTP từ cùng một kênh kiểm soát là tương đương hai yếu tố khác nhau. Đánh giá rủi ro phải dựa vào nguồn bằng chứng và khả năng bị xâm nhập chung, không dựa vào số chuỗi alias.

Nhật ký nên ghi mã tài khoản, mã liên kết, phiên bản và loại sự kiện theo nhu cầu điều tra. Hạn chế email hoặc số điện thoại đầy đủ, không ghi OTP hay liên kết chứa token. Nếu dùng HMAC của định danh để liên kết sự kiện hoặc làm khóa hạn mức, vẫn cần bảo vệ khóa và phân quyền truy cập; dữ liệu đó không tự trở thành vô danh.

Công cụ hỗ trợ cần cho phép xem và thay đổi bí danh theo quyền cụ thể, có lịch sử thao tác. Không nên cung cấp chức năng tìm toàn bộ tài khoản theo một địa chỉ cho mọi nhân viên hoặc phản chiếu lịch sử bí danh qua API công khai.

## 10. Các tình huống cần kiểm chứng khi triển khai

| Nhóm tình huống | Điều cần xác nhận |
| --- | --- |
| Username, email và số điện thoại hợp lệ | Mọi đường tra cứu dùng đúng loại, phạm vi và quy tắc chuẩn hóa |
| Hoa thường, Unicode, dấu chấm, dấu cộng | Không tự tạo tương đương ngoài chính sách; xung đột không chọn tùy tiện |
| Bí danh đang chờ, bị đình chỉ hoặc đã thu hồi | Không được dùng như liên kết khôi phục đang hoạt động |
| Email liên hệ dùng chung | Không bị dùng thành khóa duy nhất nếu không đủ điều kiện phân biệt |
| Cùng username ở hai tenant | Challenge và hành động cuối không thể vượt phạm vi tenant |
| Hai giao dịch cùng kích hoạt một bí danh | Ràng buộc lưu trữ giữ được tính duy nhất theo chính sách |
| Đổi liên kết trong khi token còn hiệu lực | Token không chuyển sang chủ mới; thay đổi bảo mật có hiệu lực đúng chính sách |
| Gửi thư chậm hoặc cache còn dữ liệu cũ | Không phát quyền dựa trên liên kết đã bị thu hồi |
| Client thay email, aliasId hoặc principalId ở bước cuối | Tài khoản đích vẫn lấy từ giao dịch đã được máy chủ ràng buộc |
| Nhiều bí danh trỏ cùng tài khoản | Không nhân số lượt gửi, số lượt đoán mã hay mức tin cậy của bằng chứng |
| Nhân viên hỗ trợ gộp hoặc chuyển bí danh | Có bằng chứng, quyền thao tác và lịch sử; không tự suy từ trùng email |

Các kiểm chứng này cần bao gồm cả đường lỗi và thay đổi đồng thời, thay vì chỉ xác nhận rằng nhập email chính có thể nhận thư. Chính sách bí danh an toàn phải giữ nguyên tài khoản đích, phạm vi và yêu cầu bằng chứng trong toàn bộ giao dịch, kể cả khi liên kết bên ngoài đã thay đổi.