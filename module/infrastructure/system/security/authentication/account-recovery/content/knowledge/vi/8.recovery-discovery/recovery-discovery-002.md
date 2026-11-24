# Tìm các kênh khôi phục đã đăng ký

Trong chương **Recovery Discovery** của module **SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY**, **discovering registered channels** là quá trình giúp người dùng xác định những kênh liên hệ đã được thiết lập cho việc khôi phục tài khoản và chọn một đường còn sử dụng được.

Khi mất mật khẩu, MFA, passkey hoặc thiết bị xác thực, người dùng có thể không nhớ email hay số điện thoại nào đã đăng ký. Hệ thống cần hướng dẫn họ mà không biến trang khôi phục thành công cụ dò tài khoản hoặc tra cứu thông tin liên hệ của người khác.

Bài toán gồm hai phần: tìm đúng những kênh mà chính sách cho phép dùng và chỉ tiết lộ thông tin phù hợp với quyền hiện tại của người yêu cầu. Việc tìm thấy hoặc hiển thị một kênh chưa chứng minh người yêu cầu kiểm soát kênh đó và chưa cấp quyền thay đổi tài khoản.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt kênh đã được lưu, đã xác minh, có hiệu lực và đủ điều kiện cho một hành động khôi phục.
- Thiết kế bước tìm kênh dành cho người chưa đăng nhập mà không công khai cấu hình tài khoản.
- Giải thích vì sao che một phần email hoặc số điện thoại chưa đủ để bảo vệ thông tin.
- Ràng buộc việc chọn và gửi bằng chứng với tài khoản, giao dịch và kênh phía máy chủ.
- Xử lý kênh đang chờ thay đổi, bị thu hồi, không còn truy cập được hoặc thay đổi trong lúc khôi phục.
- Xác định thông tin nào người dùng, nhân viên hỗ trợ và hệ thống vận hành thực sự cần xem.

## 2. Kênh khôi phục không đồng nghĩa mọi phương thức xác thực

Trong bài này, kênh khôi phục chủ yếu là địa chỉ hoặc điểm nhận thông tin mà dịch vụ có thể sử dụng theo chính sách, chẳng hạn email hoặc số điện thoại đã thiết lập.

Cần phân biệt kênh với authenticator và đường xử lý:

| Thành phần | Vai trò | Cách liên hệ với bước tìm kênh |
| --- | --- | --- |
| Email khôi phục | Có thể nhận liên kết hoặc mã theo chính sách | Có thể được chọn để gửi bằng chứng nếu đủ điều kiện |
| Số điện thoại khôi phục | Có thể nhận thông tin qua cơ chế sản phẩm hỗ trợ | Cần kiểm tra trạng thái và phạm vi sử dụng |
| Ứng dụng TOTP | Tạo mã từ bí mật đã thiết lập | Không phải địa chỉ để máy chủ gửi lại bí mật TOTP |
| Passkey hoặc khóa bảo mật | Thực hiện xác thực bằng credential đã đăng ký | Có thể là đường thay thế, không nên công khai danh sách thiết bị qua tra cứu nặc danh |
| Mã dự phòng | Bí mật khôi phục được cấp từ trước | Người dùng cung cấp mã; không gửi lại toàn bộ mã chỉ vì họ tìm được tài khoản |
| Quy trình hỗ trợ | Xử lý theo bằng chứng và thẩm quyền đã định | Không phải một kênh liên hệ mới tự chứng minh quyền sở hữu |

Một tài khoản có thể có nhiều phương thức xác thực nhưng chỉ một kênh nhận thông báo, hoặc ngược lại. Không nên dùng một danh sách chung rồi cho mọi mục quyền khôi phục giống nhau.

Ví dụ, một email dùng nhận bản tin không tự trở thành email được phép nhận liên kết gỡ MFA. Việc một số điện thoại xuất hiện trong hồ sơ giao hàng cũng không tự cấp cho số đó vai trò bảo mật.

## 3. Bốn trạng thái cần phân biệt trước khi hiển thị

Một bản ghi liên hệ cần được đánh giá qua nhiều điều kiện.

1. **Đã được lưu:** có trong dữ liệu, có thể do đăng ký, nhập hồ sơ hoặc tích hợp.
2. **Đã được xác minh:** đã hoàn thành bước kiểm tra tương ứng tại một thời điểm.
3. **Đang có hiệu lực:** đã được áp dụng, chưa bị thay thế hoặc thu hồi và không chỉ là giá trị ứng viên.
4. **Đủ điều kiện cho hành động hiện tại:** chính sách cho phép dùng kênh đó trong giao dịch và bối cảnh đang xét.

Chỉ một trường như “verified=true” không trả lời đủ cả bốn câu hỏi.

| Ví dụ | Đánh giá cần làm |
| --- | --- |
| Email mới vừa nhập nhưng chưa xác minh | Chưa được xem là kênh khôi phục đã thiết lập |
| Email ứng viên đã nhận mã nhưng yêu cầu đổi email chưa hoàn tất | Không tự coi là kênh có hiệu lực |
| Email đã xác minh nhưng bị báo có khả năng bị chiếm | Cần đánh giá theo chính sách sự cố, không mặc định an toàn |
| Số điện thoại đã bị thu hồi khỏi tài khoản | Không dùng lại chỉ vì một bản sao dữ liệu vẫn còn |
| Email có hiệu lực cho đặt lại mật khẩu | Chưa chắc đủ điều kiện để gỡ MFA hoặc thêm passkey mới |

Việc xác minh trước đây cũng không bảo đảm người yêu cầu hiện tại vẫn kiểm soát kênh. Đó là lý do bước gửi và kiểm tra bằng chứng vẫn cần tồn tại sau bước tìm kênh.

## 4. Những thông tin có thể bị lộ trong quá trình tìm kênh

Đối thủ không nhất thiết cần thấy địa chỉ đầy đủ. Những thông tin sau cũng có thể có giá trị:

- Tài khoản có tồn tại hay không.
- Có hay không có email, số điện thoại hoặc một phương thức cụ thể.
- Số lượng kênh đã đăng ký.
- Một phần tên hộp thư, miền email hoặc đuôi số điện thoại.
- Tài khoản thuộc tổ chức hoặc bên quản lý danh tính nào.
- Một kênh vừa được thay đổi, đang bị hạn chế hoặc đã bị thu hồi.

Ví dụ, trả về “không có số điện thoại trong tài khoản” sau khi người dùng nhập email đã là tiết lộ cấu hình. Hiển thị một email được che bớt vẫn có thể giúp đối thủ liên hệ hồ sơ trên nhiều dịch vụ.

### Che bớt nội dung chỉ là một biện pháp trình bày

Không có một mẫu che email hay số điện thoại bảo đảm riêng tư cho mọi tình huống. Ký tự còn lộ, độ dài, miền email và số mục đều có thể hỗ trợ suy luận.

Một giao diện hiển thị “kênh đã đăng ký” chung chung nhưng API trả địa chỉ thật vẫn làm lộ dữ liệu. Tương tự, dữ liệu trong HTML ẩn hoặc thuộc tính của phần tử không trở nên an toàn chỉ vì chưa được vẽ lên màn hình.

Cần quyết định trước **ai được biết điều gì**, rồi mới thiết kế cách trình bày. Không bắt đầu bằng giả định “che bốn ký tự là đủ”.

## 5. Hai cách tổ chức bước tìm kênh

### 5.1. Người dùng tự cung cấp kênh họ nhớ

Ở phần công khai, hệ thống có thể hỏi người dùng thử một email hoặc số điện thoại mà họ đã thiết lập trước đây. Máy chủ kiểm tra nội bộ và chỉ gửi theo đường được phép nếu có sự phù hợp.

Ưu điểm là không cần công khai danh sách kênh của tài khoản. Giới hạn là người dùng phải nhớ được thông tin đủ chính xác.

Nếu người dùng chỉ nhớ một phần, không nên biến biểu mẫu thành API tìm kiếm theo tiền tố rồi trả dần các gợi ý của tài khoản. Có thể hướng dẫn thử đường khác hoặc quy trình hỗ trợ được thiết kế cho tình huống đó.

### 5.2. Hiển thị có giới hạn sau khi đạt điều kiện

Sau khi người yêu cầu đã có bằng chứng phù hợp, chính sách có thể cho phép hiển thị một số lựa chọn để họ nhận ra kênh còn sử dụng được.

Thông tin được hiển thị nên tối thiểu cho mục đích lựa chọn. Không mặc định phải công khai toàn bộ địa chỉ, số lượng kênh hoặc lịch sử thay đổi.

Việc đạt một bước xác minh cũng không tự cho quyền xem mọi dữ liệu bảo mật. Ví dụ, quyền tiếp tục một giao dịch đặt lại mật khẩu chưa chắc cho phép xem toàn bộ phương thức MFA và các địa chỉ liên hệ của tài khoản.

| Cách tổ chức | Phù hợp khi | Giới hạn cần giữ |
| --- | --- | --- |
| Tự nhập kênh đã thiết lập | Người dùng còn nhớ thông tin liên hệ | Phản hồi công khai không xác nhận có khớp tài khoản hay không |
| Hiển thị lựa chọn sau bằng chứng phù hợp | Cần giúp nhận ra kênh và chính sách cho phép tiết lộ | Chỉ trả những mục và chi tiết cần cho giao dịch |
| Hướng dẫn phương thức khác | Người dùng không còn truy cập kênh hoặc không nhớ đủ | Không chuyển thành việc thêm kênh mới chưa được cấp quyền |
| Chuyển quy trình hỗ trợ | Sản phẩm thực sự hỗ trợ và có căn cứ xác minh phù hợp | Nhân viên không đọc lại toàn bộ liên hệ cho người chưa chứng minh quyền |

Các cách này có thể cùng tồn tại. Điểm quan trọng là mỗi bước có ranh giới tiết lộ rõ, không dùng việc biết định danh tài khoản làm quyền xem danh sách kênh.

## 6. Thiết kế phần công khai không xác nhận cấu hình tài khoản

Một phản hồi minh họa sau khi người dùng gửi thông tin là:

> Nếu thông tin phù hợp với một tài khoản và kênh khôi phục được hỗ trợ, hướng dẫn sẽ được gửi.

Câu này có thể dùng cho các trường hợp tài khoản không tồn tại, kênh không phù hợp hoặc yêu cầu được tiếp nhận theo chính sách. Kết quả nội bộ vẫn cần được xử lý chính xác, nhưng không trả toàn bộ lý do ra điểm công khai.

Một ví dụ hợp đồng phản hồi:

~~~json
{
  "status": "REQUEST_ACCEPTED",
  "message": "Nếu thông tin phù hợp, hướng dẫn sẽ được gửi.",
  "requestRef": "opaque_reference"
}
~~~

Đây là cấu trúc minh họa, không phải API bắt buộc. Nếu có mã tham chiếu, mã đó không nên trực tiếp chứa định danh tài khoản hay trở thành quyền truy cập tài khoản.

Mã tham chiếu cũng không được dẫn tới một API khác tiết lộ “đã tìm thấy tài khoản” hoặc địa chỉ nhận. Bảo vệ phản hồi đầu nhưng để lộ qua truy vấn trạng thái không giải quyết được bài toán.

### Những khác biệt ngoài câu chữ

Cần xem xét cả:

- Cấu trúc và mã phản hồi.
- Chuyển trang hoặc loại biểu mẫu tiếp theo.
- Chênh lệch thời gian xử lý có thể quan sát lặp lại.
- Đường gửi lại và cách hiển thị giới hạn thử.
- Thông tin trả từ API phụ hoặc nội dung tải sẵn.
- Các trạng thái công khai của hàng đợi và gửi thông báo.

Có thể tách việc tiếp nhận yêu cầu khỏi xử lý và gửi thông tin ở phía sau. Tuy nhiên, chỉ thêm một khoảng trễ ngẫu nhiên không tự loại bỏ khác biệt có thể suy ra qua nhiều lần quan sát.

Lỗi định dạng đầu vào, chẳng hạn trường bắt buộc bị bỏ trống, có thể được hướng dẫn theo quy tắc chung. Không nên gắn lỗi định dạng với việc xác nhận tài khoản hoặc kênh có đăng ký hay không.

### Giới hạn thực tế của việc chống dò

Phản hồi chung bảo vệ thông tin tại điểm công khai; nó không làm mọi dấu vết biến mất. Người có quyền truy cập hộp thư, nhà cung cấp kênh hoặc hệ thống vận hành vẫn có thể quan sát một phần hoạt động.

Thiết kế cần giới hạn nội dung thông báo và quyền truy cập dữ liệu phù hợp. Không nên gửi thông báo giả tới địa chỉ tùy ý chỉ để bắt chước hành vi của tài khoản thật, vì điều đó có thể tạo quấy rối và lạm dụng.

## 7. Tìm và chọn kênh phía máy chủ

Một quy trình có thể được tổ chức như sau:

1. Cố định tài khoản đích và phạm vi tổ chức trong ngữ cảnh nội bộ.
2. Xác định hành động khôi phục đang yêu cầu.
3. Tải những kênh có hiệu lực từ nguồn dữ liệu có thẩm quyền.
4. Áp dụng chính sách theo loại kênh, tình trạng xác minh và bối cảnh sự cố.
5. Xác định thông tin nào người yêu cầu được phép xem.
6. Cho chọn trong phạm vi được phép hoặc xử lý kênh người dùng tự cung cấp.
7. Kiểm tra lại điều kiện trước khi phát hành bằng chứng.
8. Gửi tới địa chỉ được máy chủ xác định từ bản ghi hợp lệ.

Điểm cuối đặc biệt quan trọng: client không được tự chọn một địa chỉ giao nhận tùy ý rồi yêu cầu máy chủ phát hành token có quyền với tài khoản đích.

Nếu biểu mẫu cho nhập email, máy chủ phải kiểm tra email đó thuộc đường được phép. Không được coi việc người dùng nhập đúng tên tài khoản là đủ để gửi liên kết khôi phục tới bất kỳ email nào họ nhập tiếp theo.

### Dùng tham chiếu có phạm vi cho lựa chọn đã hiển thị

Sau khi được phép hiển thị danh sách, máy chủ có thể trả một tham chiếu mờ cho mỗi lựa chọn. Tham chiếu nên gắn với tài khoản, giao dịch, hành động và thời hạn phù hợp.

Nó giúp tránh việc client trực tiếp truyền địa chỉ thật ở những bước không cần thiết. Tuy nhiên, “khó đoán” không thay thế kiểm tra quyền. Máy chủ vẫn phải xác minh tham chiếu thuộc đúng giao dịch và kênh còn đủ điều kiện.

Không dùng một số thứ tự toàn cục hoặc mã bản ghi dễ thay thế để chọn kênh của tài khoản khác. Việc đổi giá trị trong yêu cầu không được làm thay đổi tài khoản đích hoặc phạm vi tổ chức.

## 8. Mô hình quyết định và mã giả

Quá trình tìm kênh có thể được biểu diễn thành hai bộ lọc:

- **Bộ lọc sử dụng:** kênh có được dùng cho hành động hiện tại không?
- **Bộ lọc tiết lộ:** người yêu cầu hiện được biết những gì về kênh?

Một kênh có thể được máy chủ sử dụng để gửi thông tin mà chưa được công khai địa chỉ trên giao diện. Ngược lại, người dùng có thể biết một địa chỉ trong hồ sơ nhưng địa chỉ đó không đủ điều kiện nhận quyền khôi phục.

~~~mermaid
flowchart TD
    A[Yêu cầu tìm đường khôi phục] --> B[Xác định tài khoản, phạm vi và hành động nội bộ]
    B --> C[Tải kênh có hiệu lực và áp dụng chính sách sử dụng]
    C --> D{Người yêu cầu được phép xem lựa chọn riêng của tài khoản?}
    D -- Chưa --> E[Hướng dẫn chung hoặc nhận kênh người dùng tự cung cấp]
    D -- Có --> F[Hiển thị tối thiểu những lựa chọn được phép]
    E --> G[Kiểm tra lựa chọn hoặc thông tin phù hợp phía máy chủ]
    F --> G
    G --> H{Kênh hiện còn đủ điều kiện?}
    H -- Có --> I[Phát hành bằng chứng cho đúng giao dịch và gửi qua kênh]
    H -- Không --> J[Không cấp quyền; hướng dẫn tiếp tục theo phạm vi được phép]
    I --> K[Xác minh bằng chứng trước khi cấp quyền thay đổi]
~~~

Mã giả dưới đây minh họa bước gửi sau khi người dùng chọn một kênh đã được phép hiển thị:

~~~text
requestProofForSelectedChannel(context, channelReference):
    require context permits this recovery step
    require context.accountId and context.tenantId are fixed
    require context.action is fixed

    channel = resolveReference(
        reference = channelReference,
        transactionId = context.transactionId,
        accountId = context.accountId,
        action = context.action
    )

    require channel belongs to the same account and tenant
    require channel is effective and not revoked
    require current policy permits this channel for context.action
    require incident context does not disqualify this route
    require sending is allowed under abuse controls

    proof = issueLimitedProof(
        accountId = context.accountId,
        transactionId = context.transactionId,
        channelId = channel.id,
        action = context.action,
        expiry = policy.proofExpiry
    )

    scheduleDeliveryToServerResolvedDestination(channel, proof)
    return RESPONSE_ALLOWED_FOR_THIS_CONTEXT
~~~

Mã giả không cấp phiên đăng nhập và không xác nhận đã khôi phục xong. Nó cũng không thay thế việc xử lý lỗi, thời hạn, xung đột trạng thái và quyền một lần trong triển khai thực tế.

Đối với phần công khai chưa được phép xem lựa chọn, kết quả không tìm thấy hoặc không đủ điều kiện cần được chuyển thành phản hồi công khai phù hợp. Không trả trực tiếp mọi lỗi nội bộ của mã giả.

## 9. Kênh thay đổi giữa lúc hiển thị và gửi

Danh sách hiển thị chỉ là trạng thái tại một thời điểm. Trước khi người dùng bấm chọn:

- Email có thể đã được thay theo một giao dịch hợp lệ khác.
- Số điện thoại có thể đã bị thu hồi.
- Một kênh có thể bị đánh dấu không còn dùng cho khôi phục.
- Tài khoản có thể bị hạn chế hoặc chính sách thay đổi.
- Giao dịch hiện tại có thể hết hạn hoặc bị hủy.

Vì vậy, máy chủ cần kiểm tra lại điều kiện khi phát hành và sử dụng bằng chứng. Không chỉ tin danh sách đã tải trước đó hoặc một token có chữ ký đúng.

### Không chuyển quyền âm thầm sang địa chỉ mới

Giả sử người dùng chọn một tham chiếu từng tương ứng email A. Trong thời gian chờ, cấu hình đổi sang B.

Không nên tự biến thao tác đã chọn A thành việc phát hành quyền tới B chỉ vì trường “email hiện tại” đã đổi. Cần quy tắc rõ về phiên bản kênh, nội dung giao dịch và việc đánh giá lại.

Nếu lựa chọn đã cũ, có thể yêu cầu tải lại những lựa chọn được phép hoặc tiếp tục một đường khác. Mức chi tiết của thông báo phụ thuộc quyền hiện có, tránh dùng lỗi này để tiết lộ lịch sử thay đổi cho người chưa được phép biết.

### Kênh ứng viên không nằm trong danh sách có hiệu lực

Một email mới đã nhận mã xác minh nhưng đang chờ phê duyệt không tự trở thành địa chỉ nhận token khôi phục. Cần tách dữ liệu ứng viên khỏi dữ liệu có hiệu lực trong cơ sở dữ liệu, cache và hệ thống gửi.

Nếu hệ thống dùng bản sao hoặc hàng đợi, nội dung gửi phải giữ đúng ràng buộc đã được chấp nhận. Không chỉ lấy lại một trường liên hệ có thể đã thay mà không kiểm tra tác động tới quyền.

## 10. Khi người dùng không còn truy cập được kênh đã đăng ký

“Đã tìm thấy kênh” không có nghĩa “đã giải quyết việc mất quyền”. Người dùng có thể nhận ra email nhưng không đăng nhập được, hoặc nhận ra số điện thoại nằm trên thiết bị đã mất.

Hành trình cần có lựa chọn thực tế:

- Thử một authenticator đã đăng ký khác nếu chính sách cho phép.
- Dùng mã dự phòng còn giữ được theo đường được thiết kế.
- Thử một kênh khác đủ điều kiện mà người dùng được phép lựa chọn.
- Chuyển sang quy trình xử lý mất toàn bộ phương thức hoặc nghi bị chiếm nếu có hỗ trợ.
- Kết thúc chưa đủ căn cứ nếu không có đường phù hợp.

Không ép người dùng lặp lại bước nhận mã ở đúng kênh họ vừa báo không còn sử dụng được.

### Hai kênh khác nhau chưa chắc độc lập

Email và SMS có thể cùng được truy cập trên một thiết bị đã mất. Hai email có thể cùng phụ thuộc một tài khoản hoặc môi trường bị chiếm.

Việc hiển thị hai lựa chọn không tự tạo ra hai lớp xác minh độc lập. Chính sách cần xét quan hệ phụ thuộc và bối cảnh sự cố nếu muốn kết hợp bằng chứng.

Thiết bị mới cũng không tự là dấu hiệu người yêu cầu không hợp lệ. Chủ tài khoản có thể đang chủ động dùng môi trường khác để tránh thiết bị bị mất hoặc bị xâm nhập.

### Thêm kênh mới là một hành động khác

Email mới có thể được dùng làm địa chỉ liên lạc của hồ sơ hỗ trợ nếu quy trình cho phép. Điều đó không biến email mới thành kênh khôi phục của tài khoản.

Quyền thêm hoặc thay kênh phải đến từ quyết định khôi phục đạt điều kiện. Không tạo vòng tròn: không truy cập kênh cũ, tự nhập kênh mới, nhận mã ở kênh mới rồi dùng mã đó làm căn cứ duy nhất để tiếp quản tài khoản.

## 11. Chuẩn hóa, tài khoản liên kết và nhiều phạm vi

Thông tin người dùng nhập cần được xử lý theo quy tắc định danh của sản phẩm. Chuẩn hóa sai có thể gửi bằng chứng nhầm nơi hoặc gộp những tài khoản không cùng danh tính.

Không tự áp dụng một quy tắc xóa dấu chấm, bỏ nhãn phụ hoặc biến đổi địa chỉ cho mọi nhà cung cấp email. Với số điện thoại, cần xử lý định dạng và phạm vi phù hợp theo quy tắc đã được thiết kế, không chỉ so sánh vài chữ số cuối.

Nếu một thông tin liên hệ xuất hiện trong nhiều tài khoản hoặc nhiều tổ chức, cần giữ đúng tài khoản đích và phạm vi được phép. Không trả danh sách mọi tài khoản gắn với email cho bất kỳ ai vừa nhập email đó.

Đối với tài khoản dùng đăng nhập liên kết, ứng dụng cần biết mình quản lý kênh khôi phục nào và phần nào thuộc bên quản lý danh tính khác. Không suy luận từ miền email rồi tự tạo đường đặt lại mật khẩu cục bộ.

Chỉ hướng người dùng tới những đường quản lý đã được sản phẩm hoặc tổ chức chấp nhận. Việc chọn đường cũng cần tránh tiết lộ không cần thiết mối quan hệ giữa tài khoản và tổ chức cho người chưa có quyền.

## 12. Chống lạm dụng mà không tạo thêm nguồn tiết lộ

Bước tìm và thử kênh có thể bị sử dụng để dò định danh hoặc gửi thông tin hàng loạt. Những kiểm soát phù hợp có thể giới hạn theo nguồn yêu cầu, đích nhận, giao dịch và bối cảnh sử dụng.

Cần kiểm tra tác động đến cả bảo mật và người dùng:

- Giới hạn gửi không nên chỉ tồn tại ở giao diện.
- Gửi lại không nên tự vô hiệu hóa mọi giao dịch hợp lệ do chủ tài khoản đang thực hiện.
- Cách thông báo bị giới hạn không nên công khai kênh nào thật sự tồn tại.
- Chặn theo một tín hiệu đơn lẻ không nên mặc nhiên khóa vĩnh viễn chủ tài khoản.
- Việc gửi thất bại hoặc bị nhà cung cấp từ chối cần có xử lý nội bộ phù hợp, không tự chuyển sang gửi quyền tới một địa chỉ chưa được cấp phép.

Không nên hạ điều kiện bằng chứng chỉ vì dịch vụ gửi thông báo đang lỗi. Có thể cho thử lại, chọn đường khác được phép hoặc xử lý sự cố vận hành.

Một yêu cầu tìm kênh chưa được xác minh cũng không tự là căn cứ để thu hồi toàn bộ phiên hay thay cấu hình tài khoản. Khởi tạo khôi phục, xác minh và xử lý sự cố là những quyền cần được phân biệt.

## 13. Hỗ trợ, dữ liệu và quan sát vận hành

Nhân viên hỗ trợ có thể cần biết trạng thái một đường gửi hoặc hướng dẫn bước tiếp theo. Điều đó không có nghĩa họ cần đọc toàn bộ địa chỉ và lịch sử kênh cho mọi hồ sơ.

Phân quyền nên phù hợp với nhiệm vụ:

| Bên sử dụng | Thông tin có thể cần | Điều cần hạn chế |
| --- | --- | --- |
| Người chưa xác minh | Hướng dẫn chung, lựa chọn do họ tự khai báo | Danh sách kênh và trạng thái riêng của tài khoản |
| Người đã có quyền cho giao dịch | Lựa chọn tối thiểu được chính sách cho phép | Dữ liệu ngoài hành động đang được xử lý |
| Nhân viên hỗ trợ | Trạng thái và thông tin cần cho quy trình được giao | Tra cứu hoặc tiết lộ liên hệ không có mục đích |
| Hệ thống gửi | Đích nhận và nội dung cần thiết cho lần gửi | Quyền thay tài khoản hoặc truy cập hồ sơ vượt nhiệm vụ |
| Hệ thống phân tích | Sự kiện, kết quả và lý do ở mức cần thiết | Token, OTP, mã dự phòng và liên hệ đầy đủ không cần thiết |

Không coi việc người yêu cầu đoán đúng đuôi số điện thoại hoặc một phần email mà nhân viên đọc ra là bằng chứng sở hữu. Thông tin đó có thể đã biết từ trước hoặc bị lộ qua chính cuộc trao đổi.

Băm một email cũng không tự làm dữ liệu trở thành vô danh, vì email có thể dễ được thử và đối chiếu. Cần lựa chọn cách bảo vệ và quyền truy cập phù hợp, đồng thời giảm dữ liệu được ghi nhận ngay từ đầu.

Các chỉ số hữu ích có thể gồm tỷ lệ tiếp tục theo từng đường, số lần không nhận được thông báo, giới hạn gửi, lựa chọn đã cũ và số ca không còn kênh sử dụng được. Không nên đưa địa chỉ liên hệ đầy đủ hoặc bí mật vào sự kiện phân tích.

## 14. Những tình huống minh họa

### Tình huống A: Danh sách bị che nhưng vẫn làm lộ cấu hình

Một trang cho nhập email rồi trả hai mục: email cá nhân được che bớt và số điện thoại có bốn số cuối.

Dù chưa có địa chỉ đầy đủ, người bất kỳ đã biết tài khoản tồn tại và có hai kênh tương ứng. Cách sửa không chỉ là che thêm ký tự; cần đưa việc hiển thị danh sách sau điều kiện tiết lộ phù hợp hoặc dùng bước người dùng tự cung cấp thông tin.

### Tình huống B: Người dùng đã đủ điều kiện chọn kênh nhưng mất điện thoại

Bình đã hoàn thành một bước xác minh mà chính sách cho phép xem một số lựa chọn. Bình nhận ra số điện thoại nhưng không còn giữ thiết bị.

Hệ thống cần cho Bình chọn đường khác được phép, không coi việc số đã đăng ký là bằng chứng Bình có thể nhận mã ngay. Việc xem lựa chọn và kiểm soát lựa chọn vẫn là hai bước.

### Tình huống C: Email mới đang chờ áp dụng

Chi đang chuyển email từ A sang B. B đã nhận mã nhưng thay đổi chưa hoàn tất. Một yêu cầu khôi phục xuất hiện.

Hệ thống không đưa B vào danh sách kênh có hiệu lực chỉ vì B được xác minh trong giao dịch thay email. Nếu A bị nghi chiếm, cần đường xử lý phù hợp thay vì mặc định chọn A hoặc tự kích hoạt B.

### Tình huống D: Lựa chọn cũ sau khi kênh bị thu hồi

Dung mở một màn hình lựa chọn được phép. Trước lúc Dung bấm gửi, kênh đó bị thu hồi theo một giao dịch bảo mật hợp lệ.

Máy chủ kiểm tra lại, không phát hành bằng chứng qua kênh đã mất điều kiện. Nó cũng không tự chuyển quyền sang một đích mới mà Dung chưa chọn trong giao dịch phù hợp.

## 15. Danh sách kiểm tra khi thiết kế bước tìm kênh

Một thiết kế rõ ràng cần trả lời được:

- Đâu là dữ liệu liên hệ thông thường, đâu là kênh khôi phục đã được thiết lập?
- Kênh đã xác minh, có hiệu lực và đủ điều kiện cho hành động nào?
- Người yêu cầu được biết tài khoản, số lượng kênh và chi tiết liên hệ từ thời điểm nào?
- Mẫu che thông tin có còn tiết lộ dữ liệu không cần thiết không?
- API, HTML, chuyển trang và truy vấn trạng thái có cùng giữ giới hạn tiết lộ không?
- Client chọn một tham chiếu có phạm vi hay có thể tự chỉ định đích nhận quyền?
- Máy chủ có giữ đúng tài khoản, tổ chức, giao dịch và hành động khi gửi không?
- Kênh vừa thay, đang chờ, bị thu hồi hoặc bị nghi chiếm được xử lý thế nào?
- Người không còn truy cập được kênh có đường tiếp tục thực tế nào?
- Giới hạn lạm dụng, hỗ trợ và log có bảo vệ dữ liệu mà vẫn giải thích được quyết định không?

Tìm kênh khôi phục an toàn là giúp người dùng nhận ra và sử dụng một đường phù hợp trong giới hạn quyền hiện có. Danh sách liên hệ không phải bằng chứng sở hữu; việc gửi mã chưa cấp quyền thay đổi; và mọi lựa chọn phải được kiểm tra lại theo trạng thái thực tế của tài khoản.