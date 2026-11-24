# Kiểm soát tiết lộ thông tin khi khôi phục tên đăng nhập

## Mục tiêu và phạm vi

Trong chương **Username Recovery** của module **SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY**, khôi phục tên đăng nhập giúp người dùng nhớ lại định danh cần nhập khi đăng nhập. Thao tác này có vẻ ít nhạy cảm hơn đặt lại mật khẩu, nhưng có thể làm lộ sự tồn tại của tài khoản, quan hệ với tổ chức và cách liên kết một người với nhiều hồ sơ.

Bài học tập trung vào **username recovery disclosure**: quyết định thông tin nào được tiết lộ, cho ai, qua kênh nào và sau bằng chứng nào.

Sau bài học, người học cần có khả năng:

- Nhận diện rò rỉ trực tiếp và gián tiếp ở luồng tìm lại tên đăng nhập.
- Thiết kế phản hồi công khai không xác nhận tài khoản tồn tại.
- Xác định mức tiết lộ phù hợp sau khi kiểm tra quyền kiểm soát kênh liên hệ.
- Xử lý nhiều tài khoản, nhiều tenant, hộp thư dùng chung và kênh từng bị thay đổi.
- Giữ quyền tiết lộ tên đăng nhập tách khỏi quyền đặt lại mật khẩu, khôi phục MFA hoặc thêm passkey.
- Kiểm soát token dùng một lần, trạng thái xem kết quả, lạm dụng và dữ liệu vận hành.

Các tài khoản, tình huống, đường dẫn và chính sách trong bài là ví dụ thiết kế. Không có phần nào là kết quả kiểm thử một hệ thống thực tế.

## 1. Tên đăng nhập không phải mật khẩu nhưng vẫn cần chính sách tiết lộ

Tên đăng nhập thường không được thiết kế như một bí mật xác thực. Tuy nhiên, biết một tên đăng nhập và biết **tên đó thuộc về ai, dùng ở dịch vụ nào** là hai mức thông tin khác nhau.

Một username có thể công khai trên trang hồ sơ nhưng mối liên hệ giữa username đó với email riêng tư vẫn chưa được phép công khai.

| Thông tin được tiết lộ | Điều người quan sát có thể suy ra |
| --- | --- |
| Tên đăng nhập đầy đủ | Một định danh có thể dùng để thử đăng nhập |
| “Email này có tài khoản” | Một người có quan hệ với dịch vụ |
| “Có ba tài khoản khớp” | Một kênh liên hệ gắn với nhiều hồ sơ |
| Tên workspace hoặc tenant | Người đó liên quan đến tổ chức hoặc nhóm nào |
| Vai trò quản trị | Tài khoản có thể là mục tiêu có giá trị |
| Trạng thái bị khóa hoặc vô hiệu | Thông tin vận hành hoặc lịch sử tài khoản |
| Kênh khôi phục đã che một phần | Một phần số điện thoại hoặc địa chỉ chưa chắc đã được biết |
| Tên đăng nhập cũ | Liên kết giữa các danh tính trước và sau khi đổi tên |

Rủi ro không chỉ là hỗ trợ đoán mật khẩu. Việc tiết lộ còn có thể giúp xây danh sách mục tiêu, liên kết danh tính hoặc suy ra sự tham gia vào một dịch vụ nhạy cảm.

Vì vậy, thiết kế không nên dựa vào lập luận “username không phải bí mật nên trả về cho bất kỳ ai cũng được”. Cần đánh giá cả giá trị được trả và mối liên hệ vừa được xác nhận.

## 2. Mô hình đe dọa và ranh giới tin cậy

Những tác nhân cần xét gồm:

| Tác nhân | Khả năng hoặc dữ liệu có thể có | Mục tiêu tiết lộ |
| --- | --- | --- |
| Người ngoài biết email của nạn nhân | Danh sách email công khai hoặc bị rò rỉ | Xác nhận ai có tài khoản |
| Người kiểm soát nhiều nguồn gửi | Nhiều IP hoặc phiên trình duyệt | Dò hàng loạt với ít yêu cầu từ mỗi nguồn |
| Người có quyền vào hộp thư dùng chung | Email bộ phận hoặc gia đình | Xem username của người khác cùng dùng địa chỉ |
| Chủ mới của địa chỉ liên hệ | Hộp thư hoặc số điện thoại được cấp lại | Tìm tài khoản của chủ cũ |
| Người đã chiếm hộp thư | Đọc được email khôi phục | Liên kết và mở rộng phạm vi tấn công |
| Nhân viên hỗ trợ | Có công cụ tìm tài khoản nội bộ | Đọc hoặc xuất thông tin vượt nhu cầu xử lý |
| Người xem log hoặc analytics | Dữ liệu request, URL hoặc response | Thu thập liên kết email, username và tenant |

Cần tách ít nhất ba ranh giới:

1. **Người gọi endpoint công khai:** chưa chứng minh kiểm soát tài khoản hoặc kênh liên hệ.
2. **Người đã chứng minh kiểm soát một kênh:** có một bằng chứng hẹp, chưa tự chứng minh quyền với mọi hồ sơ từng liên quan.
3. **Người được chính sách cho xem một tập dữ liệu cụ thể:** chỉ được nhận các trường và tài khoản đã được cấp quyền.

Một thiết kế rõ ràng không nhảy thẳng từ ranh giới thứ nhất sang danh sách tất cả username.

## 3. Mức tiết lộ nên được xác định trước khi xây API

Một chính sách minh họa:

| Bối cảnh | Có thể cung cấp gì? | Không tự động cung cấp gì? |
| --- | --- | --- |
| Chưa xác minh, vừa nhập email | Hướng dẫn chung về bước tiếp theo | Username, sự tồn tại, số tài khoản, tenant liên quan |
| Đã mở thử thách qua kênh hợp lệ | Tiếp tục bước kiểm tra chính sách | Mọi tài khoản có cùng email trong lịch sử |
| Đủ điều kiện xem định danh của một tài khoản | Username hiện tại cần để đăng nhập | Vai trò, dữ liệu hồ sơ hoặc bí mật xác thực |
| Đủ điều kiện xem một tập tài khoản đã xác định | Danh sách tối thiểu trong đúng phạm vi đó | Tài khoản ngoài phạm vi, tenant khác chưa được cấp quyền |
| Đã đăng nhập và xác thực phù hợp | Thông tin theo quyền của session hiện tại | Quyền truy cập tài khoản khác chỉ vì cùng email |
| Mất quyền kiểm soát kênh | Hướng dẫn hỗ trợ hoặc phương án đã đăng ký khác | Gợi ý định danh dựa vào tiểu sử dễ tìm |

“Đã xác minh” phải chỉ rõ **đã xác minh điều gì**. Ví dụ, mở một liên kết gửi đến hộp thư cho biết người yêu cầu tiếp cận được liên kết đó; điều này không tự chứng minh họ là người duy nhất đọc hộp thư hoặc là chủ tài khoản từ thời điểm đăng ký.

Có thể áp dụng yêu cầu bằng chứng cao hơn khi tên đăng nhập hoặc quan hệ với dịch vụ có mức nhạy cảm cao. Ngược lại, một dịch vụ có định danh công khai vẫn cần kiểm soát việc liên kết định danh đó với email riêng tư.

## 4. Rò rỉ có thể nằm ngoài thông báo hiển thị

### 4.1. Trả username trực tiếp

Thiết kế yếu:

~~~http
POST /account/username-recovery

{
  "email": "linh@example.test"
}
~~~

~~~json
{
  "found": true,
  "username": "linh.study",
  "tenant": "engineering-class",
  "role": "ADMIN"
}
~~~

Người gọi chỉ biết email đã nhận được cả định danh đăng nhập và thông tin quyền hạn.

Sửa giao diện để chỉ hiện “Đã tiếp nhận” không giải quyết được nếu JSON vẫn chứa những trường trên. Người quan sát có thể đọc response mà không dùng giao diện.

### 4.2. Username đã che vẫn có thể tiết lộ

Các giá trị như “li***dy” hoặc “Có tài khoản l***” vẫn xác nhận rằng một kết quả khớp đã được tìm thấy. Với một tập ứng viên nhỏ, phần còn lại có thể đủ để suy ra tên đầy đủ.

Che thông tin là biện pháp giảm dữ liệu sau một quyết định tiết lộ; nó không thay thế quyết định người nhận có quyền biết tài khoản đó tồn tại hay không.

Không nên gửi danh sách đầy đủ xuống client rồi chỉ che bằng CSS. Dữ liệu trong DOM, thuộc tính HTML, state của ứng dụng hoặc response vẫn có thể bị đọc.

### 4.3. Tín hiệu qua HTTP, điều hướng và giao diện

| Khác biệt | Ví dụ rò rỉ |
| --- | --- |
| Mã trạng thái | Email có tài khoản nhận 202, email không có nhận 404 |
| Cấu trúc response | Có tài khoản mới có trường deliveryStatus |
| Số lượng phần tử | Danh sách trống khác danh sách chứa một phần tử đã che |
| Redirect | Chỉ tài khoản hợp lệ được chuyển tới trang nhập mã |
| Cookie | Chỉ kết quả khớp mới nhận cookie đặc biệt |
| Nút gửi lại | Chỉ hiện đếm ngược khi thực sự tìm thấy kênh |
| Lỗi nhà cung cấp | Chỉ tài khoản có thật mới trả lỗi gửi email |
| URL kết quả | Đường dẫn chứa username, tenant hoặc mã người dùng |

OWASP khuyến nghị phản hồi chung trong các luồng xác thực và khôi phục, đồng thời cảnh báo khác biệt về mã HTTP hoặc thời gian có thể hỗ trợ dò tài khoản. Xem [OWASP Authentication: Authentication and Error Messages](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#authentication-and-error-messages).

Đây là một trường hợp áp dụng nguyên tắc tránh **observable discrepancy**: thông tin bí mật bị suy ra từ khác biệt có thể quan sát. Xem [CWE-203](https://cwe.mitre.org/data/definitions/203.html).

## 5. Thiết kế phần tiếp nhận công khai

### 5.1. Phản hồi có điều kiện, không khẳng định đã gửi

Một thông báo phù hợp:

> Nếu thông tin bạn cung cấp khớp với tài khoản đủ điều kiện, hướng dẫn sẽ được gửi qua kênh đã đăng ký. Hãy kiểm tra hộp thư và thư mục thư rác.

Không dùng “Chúng tôi đã gửi username của bạn” nếu có thể không tồn tại tài khoản hoặc không đủ điều kiện tiết lộ.

Response minh họa:

~~~http
HTTP/1.1 202 Accepted
Cache-Control: no-store
Content-Type: application/json
~~~

~~~json
{
  "code": "USERNAME_RECOVERY_ACCEPTED",
  "message": "Nếu thông tin khớp với tài khoản đủ điều kiện, hướng dẫn sẽ được gửi qua kênh đã đăng ký.",
  "requestId": "opaque-request-reference"
}
~~~

RequestId phải được tạo theo cùng cách cho mọi yêu cầu được tiếp nhận, không chứa username, accountId hoặc kết quả tra cứu được mã hóa.

HTTP 202 biểu thị đã tiếp nhận xử lý, không bảo đảm tác vụ đã hoàn tất hoặc sẽ thành công. Việc dùng mã này không tự ngăn dò tài khoản; nội dung và hành vi vẫn cần thiết kế đúng. Xem [RFC 9110, mục 15.3.3](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.3.3).

### 5.2. Lỗi đầu vào không phải kết quả tra cứu

Có thể báo định dạng đầu vào không được hỗ trợ hoặc request quá lớn nếu quyết định đó không cần biết tài khoản có tồn tại hay không.

Ví dụ, từ chối một email sai cú pháp khác với trả lỗi “email hợp lệ nhưng chưa đăng ký”.

Tương tự, lỗi hệ thống tiếp nhận có thể được thông báo khi hàng đợi không hoạt động. Không được chỉ để lỗi gửi email của nhánh có tài khoản lọt ra response công khai.

### 5.3. Không cung cấp trạng thái gửi qua một cửa khác

Một API tiếp nhận có response chung vẫn có thể rò rỉ nếu endpoint tra cứu requestId trả về:

~~~json
{
  "matchedAccounts": 2,
  "emailSent": true,
  "deliveryAddress": "l***@example.test"
}
~~~

Nếu cần cho người dùng theo dõi việc tiếp nhận, chỉ cung cấp trạng thái phù hợp với quyền hiện tại, không biến requestId thành quyền xem kết quả tra cứu hoặc trạng thái tài khoản.

Trong ví dụ của bài, phần công khai không có API cho biết tìm thấy bao nhiêu tài khoản hoặc email đã được gửi cho tài khoản nào.

## 6. Thời gian phản hồi: tách tra cứu và gửi khỏi đường công khai

Thiết kế đồng bộ dễ tạo khác biệt:

~~~text
Không có tài khoản:
    tra cứu -> trả response

Có tài khoản:
    tra cứu -> tạo thử thách -> gọi dịch vụ email -> trả response
~~~

Ngay cả khi thông báo giống nhau, hai nhánh vẫn có thể khác đáng kể về độ trễ. CWE mô tả lớp rủi ro này trong [CWE-208: Observable Timing Discrepancy](https://cwe.mitre.org/data/definitions/208.html).

Một phương án là đưa cả yêu cầu hợp lệ về định dạng vào cùng đường tiếp nhận và xử lý nền. Việc tìm kết quả khớp, quyết định gửi và gọi nhà cung cấp diễn ra sau khi response công khai đã được quyết định.

### Mã giả Java cho phần tiếp nhận

Các API dưới đây chỉ minh họa trách nhiệm; không phải lớp thư viện có sẵn.

~~~java
RecoveryAck requestUsername(
        UsernameRecoveryRequest request,
        RequestSource source) {

    PublicScope scope = scopes.fromPublicRequest(request.workspaceKey());
    SubmittedContact contact = contacts.parseSubmitted(request.contact());

    // Áp dụng cả khi định danh không khớp tài khoản nào.
    intakeLimits.requireAllowed(scope, contact, source);

    RequestId requestId = ids.newOpaqueRequestId();

    // Hàng đợi bảo vệ dữ liệu và giới hạn thời gian lưu.
    intakeQueue.enqueueProtected(
            new UsernameLookupRequested(requestId, scope, contact));

    return RecoveryAck.accepted(requestId);
}
~~~

Các bước trước response không tra cứu để quyết định có tạo requestId, có ghi hàng đợi hay có trả cấu trúc khác hay không.

Scope ở đây phải là phạm vi được phép đưa vào yêu cầu công khai. Nếu tên tenant là thông tin riêng tư, không dùng chức năng này để trả danh sách tenant mà người dùng thuộc về.

OWASP đề cập xử lý bất đồng bộ như một cách giảm khác biệt thời gian ở luồng khôi phục mật khẩu. Bài học áp dụng cùng mục tiêu chống dò cho phần tiếp nhận khôi phục username. Xem [OWASP Forgot Password: Forgot Password Request](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#forgot-password-request).

### Chờ ngẫu nhiên không xóa được khác biệt có hệ thống

Giả sử độ trễ của hai nhánh có trung bình khác nhau. Thêm nhiễu ngẫu nhiên không tự làm hai trung bình bằng nhau.

Trong mô hình đơn giản có nhiễu độc lập, sai số của trung bình mẫu giảm theo quy mô xấp xỉ 1/sqrt(N). Vì vậy, một người quan sát nhiều lần vẫn có thể phân biệt một khác biệt ổn định.

Không cần hứa rằng mọi request có thời gian tuyệt đối giống nhau. Mục tiêu thực tế là loại bỏ khác biệt do trạng thái tài khoản khỏi đường phản hồi công khai và đo lại hành vi của cả hệ thống khi có tải.

## 7. Xác minh kênh và quyết định tiết lộ là hai bước riêng

### 7.1. Chỉ dùng quan hệ liên hệ đã được thiết lập

Khi xử lý nền, cần tìm các quan hệ liên hệ đang hoạt động và đủ điều kiện trong đúng phạm vi. Không gửi username tới một địa chỉ mới chỉ vì người gọi điền địa chỉ đó ở trường nhận kết quả.

Ví dụ yếu:

~~~text
Tìm tài khoản bằng email cũ.
Gửi username tới newEmail do người gọi cung cấp.
~~~

Người gọi chưa chứng minh quyền chuyển kết quả sang newEmail. Thay địa chỉ khôi phục cần quy trình riêng.

Ngay cả địa chỉ có trong cơ sở dữ liệu cũng cần xét trạng thái: đã xác minh chưa, đã bị thay thế chưa, có bị thu hồi không và tài khoản có đang trong tình huống rủi ro hay không.

Chuẩn hóa địa chỉ phải theo hợp đồng định danh của hệ thống. Không tự bỏ dấu chấm, bỏ phần sau dấu cộng hoặc gộp địa chỉ bằng quy tắc của một nhà cung cấp nếu hệ thống chưa thiết lập quan hệ tương đương đó.

### 7.2. Quyền đọc email hiện tại có giới hạn

Các tình huống sau không tương đương nhau:

| Tình huống | Điều chưa thể kết luận chỉ từ việc mở được email |
| --- | --- |
| Hộp thư dùng chung của bộ phận | Người mở là chủ của từng tài khoản gắn vào hộp thư |
| Email của phụ huynh dùng cho nhiều người | Mọi hồ sơ đều được phép tiết lộ cùng nhau |
| Email công ty đã cấp lại cho nhân viên mới | Người hiện tại là người đã đăng ký tài khoản cũ |
| Hộp thư bị chiếm | Người mở liên kết là chủ tài khoản hợp pháp |
| Địa chỉ đã đổi gần đây | Quan hệ mới đủ tin cậy cho thao tác nhạy cảm |

Chính sách có thể yêu cầu thêm bằng chứng đã thiết lập trước, dùng phương thức xác thực còn giữ hoặc chuyển sang hỗ trợ có kiểm soát.

Không dùng việc người yêu cầu biết username khác, ngày sinh hoặc địa chỉ cũ để tự bù cho bằng chứng còn thiếu.

### 7.3. Hai cách phân phối kết quả cần được lựa chọn rõ ràng

**Gửi username trực tiếp qua kênh đã đăng ký:** đơn giản nhưng nội dung có thể xuất hiện trong thông báo màn hình khóa, hộp thư chia sẻ và lịch sử email. Nếu được chọn, đó là một quyết định tiết lộ có chủ ý.

**Gửi liên kết tới trang tiết lộ có giới hạn:** email không chứa username; trang đích áp dụng thời hạn, phạm vi và kiểm tra chính sách trước khi hiển thị. Cách này giảm một số bản sao nhưng liên kết trở thành bí mật mang quyền, vẫn cần bảo vệ.

Không có phương án nào bảo đảm người nhận không sao chép hoặc chuyển tiếp dữ liệu sau khi đã được xem. Cần đánh giá đối tượng nhận và độ nhạy cảm, không chỉ phương tiện truyền tải.

## 8. Nhiều tài khoản và nhiều tenant

Một địa chỉ liên hệ có thể gắn với nhiều tài khoản. Điều đó không tự tạo quyền tra cứu toàn cục.

### Trước khi đủ điều kiện tiết lộ

Không trả:

- “Bạn có ba tài khoản.”
- Danh sách tên tenant để người yêu cầu chọn.
- Username đã che của từng hồ sơ.
- Gợi ý rằng tài khoản quản trị đang dùng một kênh khác.
- Trạng thái “tài khoản tồn tại nhưng bị khóa”.

Những dữ liệu này đã là kết quả tiết lộ, dù chưa có username đầy đủ.

### Sau khi đủ điều kiện

Chỉ trả tập tài khoản mà chính sách đã cho phép. Nếu có nhiều kết quả được phép, danh sách tối thiểu có thể gồm username hiện tại và nhãn phân biệt không nhạy cảm.

Không mặc nhiên thêm vai trò, ngày đăng ký, hoạt động cuối hoặc dữ liệu cá nhân để người dùng “nhận ra tài khoản”.

Truy vấn phải giữ tenant và phạm vi được cấp quyền. Không chỉ tìm theo email rồi ghép mọi kết quả từ tất cả tenant.

Nếu tài khoản dùng cùng email trong hai tổ chức nhưng quyền mới chỉ cho phép xem một tổ chức, danh sách của tổ chức còn lại không được xuất hiện trong response, mã lỗi hoặc trường totalCount.

Nguyên tắc quyền tối thiểu và kiểm tra quyền trên từng request được trình bày trong [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html). Ở đây, đối tượng cần phân quyền chính là dữ liệu định danh sắp được tiết lộ.

### Khi username đã thay đổi

Grant nên liên kết với định danh nội bộ ổn định và phạm vi, thay vì coi username cũ là căn cứ xác định chủ thể.

Khi hiển thị, đọc username hiện tại theo quyền còn hiệu lực. Không tự trả thêm lịch sử username hoặc bí danh cũ vì dữ liệu đó có thể tạo liên kết danh tính mà người dùng đã chủ ý thay đổi.

## 9. Luồng tiết lộ bằng token có quyền hạn hẹp

Ví dụ sau chọn gửi liên kết rồi hiển thị username trên một trang ngắn hạn.

~~~mermaid
sequenceDiagram
    participant U as Người yêu cầu
    participant P as Endpoint công khai
    participant W as Xử lý nền
    participant C as Kênh đã đăng ký
    participant D as Dịch vụ tiết lộ

    U->>P: Gửi thông tin liên hệ và phạm vi được phép
    P-->>U: Phản hồi tiếp nhận chung
    P->>W: Đưa yêu cầu vào hàng đợi bảo vệ dữ liệu
    W->>W: Kiểm tra quan hệ liên hệ và chính sách
    W->>C: Gửi liên kết nếu đủ điều kiện
    U->>D: Mở liên kết
    D-->>U: Trang xác nhận trung tính, chưa hiện username
    U->>D: Xác nhận xem kết quả bằng POST
    D->>D: Kiểm tra lại, tiêu thụ grant và tạo quyền xem hẹp
    D-->>U: Hiển thị dữ liệu tối thiểu được phép
~~~

### Thuộc tính của grant

| Thuộc tính | Mục đích |
| --- | --- |
| Purpose USERNAME_DISCLOSURE | Không dùng để đặt lại mật khẩu hoặc thay MFA |
| Danh sách tham chiếu tài khoản được phép | Không tự mở rộng kết quả khi có tài khoản mới |
| Tenant hoặc phạm vi được phép | Giới hạn quan hệ tổ chức được tiết lộ |
| Mã quan hệ liên hệ và phiên bản | Phát hiện kênh bị đổi, thu hồi hoặc thay thế |
| Danh sách trường được phép | Chỉ trả thông tin cần thiết |
| Thời điểm cấp, hết hạn và trạng thái | Giới hạn vòng đời |
| Liên kết với context phía máy chủ | Tách bước mở liên kết khỏi bước tiêu thụ |

Token có thể là chuỗi ngẫu nhiên khó đoán, chỉ tham chiếu dữ liệu phía máy chủ. Ví dụ dùng 32 byte ngẫu nhiên từ bộ sinh an toàn là một lựa chọn thiết kế, không phải thông số bắt buộc cho mọi giao thức.

Không đưa username hoặc danh sách tenant vào payload chỉ được ký rồi cho rằng chúng đã bí mật. Chữ ký bảo vệ tính toàn vẹn, không tự che nội dung.

Với token ngẫu nhiên có độ bất định cao, có thể lưu bộ kiểm tra dạng hash theo thiết kế thay vì lưu nguyên token. Không suy rộng cách này thành việc dùng hash nhanh để lưu mật khẩu hoặc câu trả lời dễ đoán.

### Không tiêu thụ hoặc tiết lộ chỉ vì GET

Hệ thống quét email có thể mở liên kết trước người dùng. Trong thiết kế này, GET chỉ kiểm tra sơ bộ và chuẩn bị trang xác nhận trung tính; không trả username trong HTML và không tiêu thụ grant thành công.

POST xác nhận kiểm tra lại quyền và thực hiện chuyển trạng thái. Khi dùng cookie cho context, request này cần cơ chế CSRF phù hợp.

Điều khiển xác nhận không chứng minh người bấm là người thật hoặc là chủ tài khoản. Nó giúp tách việc tải tài nguyên khỏi thao tác tiết lộ; bằng chứng và chính sách vẫn quyết định quyền.

Sau khi tiêu thụ, có thể cấp context chỉ đọc ngắn hạn để xem kết quả. **Token được dùng một lần không có nghĩa username chỉ có thể bị nhìn thấy một lần.** Context xem, thời hạn và chính sách đọc lại phải được xác định riêng.

## 10. Mã giả xử lý nền và bước tiết lộ

### 10.1. Chỉ gửi qua quan hệ liên hệ được chính sách chấp nhận

~~~java
void process(UsernameLookupRequested event) {
    DisclosurePlan plan = disclosurePolicy.planFromActiveBindings(
            event.scope(),
            event.contact());

    if (!plan.isEligible()) {
        // Trạng thái nội bộ không được công khai qua requestId.
        processing.finishWithoutPublicDetails(event.requestId());
        return;
    }

    if (!deliveryLimits.tryAcquire(plan.deliveryBindingId())) {
        processing.finishWithoutPublicDetails(event.requestId());
        return;
    }

    UsernameDisclosureGrant grant = grants.issueUsernameOnly(
            plan.allowedAccountRefs(),
            plan.scope(),
            plan.allowedFields(),
            plan.deliveryBindingId(),
            plan.bindingVersion(),
            plan.expiresAt());

    // Kiểm tra lại trạng thái binding trước khi gửi.
    // Dùng khóa chống gửi trùng cho cùng tác vụ.
    delivery.sendNeutralLinkToRegisteredBinding(
            grant,
            event.requestId());
}
~~~

DisclosurePlan phải là kết quả của chính sách phía máy chủ, không phải danh sách accountId hoặc allowedFields do người gọi gửi lên.

Email trong ví dụ không chứa username. Subject và phần xem trước cũng không thêm vai trò, số tài khoản hoặc tenant riêng tư.

Nhà cung cấp gửi email, hàng đợi và cơ chế retry phải được kiểm soát dữ liệu. Việc gửi lại do lỗi tạm thời không được làm phát sinh vô hạn liên kết hoặc làm mới thời hạn grant.

### 10.2. Kiểm tra lại khi người nhận yêu cầu xem

~~~java
DisclosureResult disclose(
        DisclosureRequest request,
        HttpRequest http) {

    PendingDisclosureContext context = contexts.require(http);
    csrf.requireValid(context, request.csrfToken(), http);
    limits.requireAllowed(context, http);

    return transaction.run(() -> {
        UsernameDisclosureGrant grant = grants.lock(context.grantId());

        grants.requireAvailable(
                grant,
                Purpose.USERNAME_DISCLOSURE,
                database.currentTime());

        ContactBinding binding = bindings.lock(grant.bindingId());

        DisclosureDecision decision = disclosurePolicy.revalidate(
                context,
                grant,
                binding,
                grant.allowedAccountRefs());

        if (!decision.mayDisclose()) {
            return DisclosureResult.requireFurtherVerification();
        }

        grant.consume();

        ReadOnlyDisclosureView view = views.activate(
                context,
                decision.allowedAccountRefs(),
                decision.allowedFields(),
                decision.viewExpiresAt());

        audit.recordDisclosureGranted(
                grant.id(),
                decision.policyVersion());

        return DisclosureResult.viewReady(view.opaqueReference());
    });
}
~~~

Đây là mã giả; ví dụ giả định các bước chuyển trạng thái có thể phối hợp trong cùng transaction. Một triển khai phân tán phải có cơ chế nhất quán tương ứng, không chỉ sao chép thứ tự gọi hàm.

Việc kiểm tra lại cần xét:

- Grant chưa dùng, chưa hết hạn, chưa bị thu hồi và đúng mục đích.
- Context thuộc đúng grant, không bị ghép với yêu cầu khác.
- Quan hệ liên hệ và phiên bản vẫn hợp lệ.
- Danh sách tài khoản vẫn nằm trong phạm vi đã cấp.
- Chính sách hiện tại còn cho phép tiết lộ.
- Thời hạn view không vượt các giới hạn mà chính sách cho phép.

Trang đọc kết quả tiếp tục kiểm tra context và quyền, chỉ đọc các trường được phép của tài khoản trong phạm vi. Không dùng một opaqueReference như quyền xem mọi hồ sơ hoặc dựa vào việc mã khó đoán để bỏ kiểm tra.

Nếu liên hệ bị thu hồi sau khi view được tạo, chính sách đọc phải xử lý được việc đó. Không để một snapshot chứa username sống vô hạn chỉ vì token ban đầu từng hợp lệ.

## 11. Hiển thị và phân phối dữ liệu tối thiểu

Khi đã đủ quyền, kết quả nên rõ ràng về việc người dùng nhận được gì:

~~~text
Tên đăng nhập của tài khoản trong phạm vi đã xác minh:

linh.study

Bạn có thể dùng tên này tại trang đăng nhập.
Nếu quên mật khẩu hoặc mất phương thức MFA,
hãy sử dụng quy trình khôi phục tương ứng.

[Đến trang đăng nhập]
~~~

Không hiển thị mật khẩu, mã khôi phục, danh sách thiết bị hoặc vai trò chỉ để làm kết quả trông đầy đủ hơn.

### Không để dữ liệu rò qua đường phụ

- Render username như văn bản bằng cơ chế mã hóa đầu ra phù hợp, không ghép thành HTML tin cậy.
- Không đưa username hoặc token vào URL trang kết quả.
- Không tự gửi username cho analytics, công cụ ghi lại phiên hoặc script bên thứ ba.
- Không tự sao chép vào clipboard; chỉ hỗ trợ sao chép khi người dùng chủ động chọn.
- Không dùng kết quả trong thông báo đẩy hoặc tiêu đề email nếu chính sách chưa cho phép.
- Nếu chuyển tới đăng nhập, dùng đường dẫn tin cậy; không truyền định danh trong query chỉ để tự điền.
- Nếu cần giữ lựa chọn trong cùng hệ thống, dùng cơ chế hẹp phía máy chủ, không tạo session đăng nhập.

Các trang nhận token và hiển thị kết quả cần chính sách cache và referrer phù hợp, chẳng hạn:

~~~http
Cache-Control: no-store
Referrer-Policy: no-referrer
~~~

Những header này không xóa dữ liệu đã đi vào email, log hoặc bản sao do người nhận tạo. Cần giảm dữ liệu ở cả khâu thu thập, phân phối và lưu giữ.

Việc đánh giá quyền riêng tư nên xét cả mối liên hệ giữa các dữ kiện, không chỉ từng trường riêng lẻ. Xem [OWASP User Privacy Protection](https://cheatsheetseries.owasp.org/cheatsheets/User_Privacy_Protection_Cheat_Sheet.html).

### Giới hạn bảo mật cần nói rõ

Một khi username đã hiện cho người nhận, dịch vụ không thể bảo đảm họ không ghi lại hoặc chuyển tiếp. View hết hạn chỉ ngăn các lần truy cập sau theo cơ chế của hệ thống; nó không thu hồi được trí nhớ hoặc bản sao đã có.

Đó là lý do cần quyết định đúng trước khi tiết lộ, thay vì dựa hoàn toàn vào thời gian hiển thị ngắn.

## 12. Chống lạm dụng mà không tạo tín hiệu mới

Luồng này có thể bị dùng để dò tài khoản, gửi email hàng loạt, gây phiền nhiễu hoặc tiêu tốn tài nguyên.

### Ngân sách tiếp nhận và ngân sách gửi

Cần phân biệt:

| Ngân sách | Cách áp dụng |
| --- | --- |
| Tiếp nhận theo nguồn gửi | Hạn chế một nguồn tạo quá nhiều yêu cầu |
| Tiếp nhận theo định danh được cung cấp | Áp dụng cả khi định danh không có tài khoản |
| Theo phạm vi hoặc toàn dịch vụ | Bảo vệ hệ thống trước nguồn phân tán |
| Gửi tới kênh đã đăng ký | Giới hạn số email thực sự gửi trong xử lý nền |
| Đổi token lấy quyền xem | Giới hạn thử token và tạo context |

Nếu chỉ định danh có tài khoản mới gặp cooldown công khai, cooldown lại trở thành tín hiệu tồn tại. Giới hạn gửi thực tế có thể được xử lý nền mà không trả “đã tìm thấy nhưng gửi quá nhiều lần” cho người chưa được xác minh.

Không chỉ giới hạn theo IP. Đồng thời, không để một người ngoài gửi nhiều yêu cầu làm khóa mọi cách đăng nhập hợp lệ của nạn nhân.

### Bảo vệ khóa dùng để tương quan

Có thể cần tương quan các lần gửi theo định danh chuẩn hóa. Không mặc định hash nhanh của email làm dữ liệu trở nên ẩn danh: miền giá trị có thể được đoán và kiểm tra lại.

Một khóa giả danh bằng HMAC với bí mật máy chủ là một lựa chọn cho mục đích hẹp, nhưng vẫn cần quản lý khóa, thời hạn lưu và quyền truy cập. Dữ liệu có thể liên kết các lần yêu cầu vẫn là dữ liệu cần bảo vệ.

### Không gửi nội dung cho mọi địa chỉ để giả lập hoạt động

Gửi email tới cả địa chỉ không khớp có thể tạo thêm thư rác, chi phí và cách lạm dụng dịch vụ gửi. Không cần xem đây là biện pháp mặc định để làm hai nhánh giống nhau.

Trong thiết kế minh họa, người gọi công khai không được biết kết quả gửi. Người đọc được kênh nhận có thể quan sát việc có thư hoặc nội dung tiếp theo; mức thông tin cho nhóm đó phải được đánh giá riêng theo chính sách.

Phản hồi công khai chống dò không có nghĩa hệ thống bảo đảm che được mọi quan hệ với dịch vụ khỏi một người đã chiếm kênh liên hệ.

## 13. Log, công cụ hỗ trợ và các kênh truy cập khác

### 13.1. Log không được trở thành danh bạ tài khoản

Có thể ghi sự kiện theo loại:

~~~text
USERNAME_RECOVERY_REQUEST_ACCEPTED
USERNAME_DISCLOSURE_LINK_ISSUED
USERNAME_DISCLOSURE_GRANTED
USERNAME_DISCLOSURE_DENIED
USERNAME_DISCLOSURE_EXPIRED
~~~

Dữ liệu đi kèm chỉ nên đủ cho điều tra và vận hành trong hệ thống được phân quyền. Nếu cần tham chiếu nội bộ, không dùng trường đó như dữ liệu public trong response.

Không ghi nguyên:

- Token, cookie hoặc CSRF token.
- URL đầy đủ có tham số mang quyền.
- Response chứa danh sách username.
- Toàn bộ địa chỉ liên hệ nếu mục đích log không cần.
- Quan hệ email, username và tenant vào nhãn metric hoặc analytics.

OWASP phân biệt dữ liệu cần ghi với dữ liệu phải loại bỏ hoặc bảo vệ đặc biệt, bao gồm token và dữ liệu cá nhân. Xem [OWASP Logging: Data to exclude](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#data-to-exclude).

Hàng đợi và dead-letter queue cũng có thể chứa đầu vào liên hệ. Cần hạn chế quyền đọc, bảo vệ nội dung và có vòng đời lưu giữ, không chỉ che log của ứng dụng web.

### 13.2. Nhân viên hỗ trợ cũng cần ranh giới tiết lộ

Nếu API công khai không tiết lộ username nhưng nhân viên đọc tên đó chỉ sau khi người gọi nói đúng email hoặc ngày sinh, đường tiết lộ vẫn còn.

Công cụ hỗ trợ cần tách:

- Quyền tìm hồ sơ để xử lý sự cố.
- Quyền xem những trường nào.
- Quyền tiết lộ cho người đang liên hệ.
- Quyền thay đổi phương thức khôi phục.

Một nhân viên nhìn được hồ sơ không có nghĩa mọi người gọi đều được nghe nội dung hồ sơ đó. Những lần truy cập và tiết lộ nhạy cảm cần được ghi nhận theo chính sách.

### 13.3. Không chỉ sửa một endpoint

Cần xem cùng một loại rò rỉ ở đăng nhập, đăng ký, yêu cầu mật khẩu mới, API di động, công cụ tìm thành viên và giao diện quản trị.

Việc khóa một đường tiết lộ không hiệu quả nếu đường khác vẫn trả “email đã tồn tại” hoặc danh sách tài khoản cho cùng người gọi mà không có căn cứ phù hợp. Mức công khai của từng chức năng cần được quyết định có chủ ý.

## 14. Ví dụ xuyên suốt: một email liên quan đến hai phạm vi

Linh quên username ở một hệ thống học tập. Địa chỉ linh@example.test cũng từng được dùng cho một tài khoản trong một nhóm riêng tư. Mọi dữ liệu trong ví dụ đều giả định.

Thiết kế yếu trả:

~~~json
{
  "accounts": [
    {
      "username": "linh.study",
      "workspace": "engineering-class"
    },
    {
      "username": "linh.private",
      "workspace": "private-community"
    }
  ]
}
~~~

Người chỉ biết email đã được xác nhận cả hai quan hệ.

Thiết kế thay thế:

1. Endpoint tiếp nhận trả thông báo chung, không nói có hai tài khoản.
2. Phạm vi yêu cầu được giữ trong khuôn khổ mà giao diện đó cho phép, không tra cứu để quảng bá các nhóm riêng tư.
3. Xử lý nền đánh giá quan hệ liên hệ hiện tại và chính sách của phạm vi học tập.
4. Nếu đủ điều kiện, hệ thống gửi liên kết trung tính qua kênh đã đăng ký.
5. Khi Linh yêu cầu xem, máy chủ kiểm tra lại grant và quan hệ liên hệ.
6. Kết quả chỉ cho biết linh.study nếu đó là tập được cấp quyền; không kèm totalCount của các phạm vi khác.
7. Linh dùng username tại trang đăng nhập và vẫn phải thực hiện mật khẩu, MFA hoặc passkey theo luồng bình thường.

Nếu hộp thư này là địa chỉ dùng chung hoặc đang có dấu hiệu bị chiếm, chính sách có thể yêu cầu thêm bằng chứng trước bước 6. Hệ thống không coi việc email từng được xác minh nhiều năm trước là bảo đảm vĩnh viễn về người hiện tại.

Nếu Linh đồng thời mất mật khẩu và thiết bị MFA, chức năng xem username chỉ giải quyết việc nhớ định danh. Không dùng grant tiết lộ để tự chuyển sang đặt lại mật khẩu, tắt MFA hoặc đăng ký khóa mới.

## 15. Các tình huống cần kiểm chứng khi triển khai

Bảng dưới mô tả kết quả mong muốn để xây dựng kiểm tra, không phải kết quả kiểm thử đã chạy.

| Tình huống | Kết quả mong muốn |
| --- | --- |
| Email hợp lệ có tài khoản so với không có tài khoản | Phản hồi công khai không xác nhận kết quả tra cứu |
| Tài khoản hoạt động so với bị vô hiệu | Không công khai trạng thái qua nội dung hoặc mã HTTP |
| Kênh chưa xác minh hoặc đã bị thay thế | Không tự gửi username qua quan hệ không còn đủ điều kiện |
| Người gọi yêu cầu gửi kết quả tới địa chỉ mới | Không chuyển dữ liệu sang kênh đó chỉ theo request |
| Có một, nhiều hoặc không có tài khoản khớp | Không lộ số lượng trước khi được cấp quyền |
| Cùng email ở nhiều tenant | Không mở rộng kết quả ra ngoài phạm vi được phép |
| Response chung nhưng client có state chứa username | Bị coi là rò rỉ và phải loại bỏ dữ liệu khỏi response |
| Chỉ nhánh có tài khoản gọi dịch vụ email chậm | Độ trễ đó không được đi vào response công khai |
| Chỉ tài khoản có thật bị chặn gửi | Không trả trạng thái gửi hoặc cooldown làm lộ kết quả |
| Thử theo nhiều IP | Có kiểm soát theo định danh và phạm vi ngoài IP |
| Nhập nhiều biến thể của cùng địa chỉ | Dùng hợp đồng định danh nhất quán, không tự gộp sai |
| Hệ thống quét email mở GET | Chưa nhận username và chưa tiêu thụ grant thành công |
| Token bị dùng sai mục đích | Không cho đặt mật khẩu, thay MFA hoặc thêm passkey |
| Hai request đồng thời tiêu thụ một grant | Chỉ một lần chuyển sang quyền xem được tạo hợp lệ |
| Kênh bị đổi sau khi phát token | Bước tiết lộ phát hiện thay đổi theo chính sách |
| Username đổi trước khi xem kết quả | Không trả lịch sử tên cũ ngoài quyền đã cấp |
| Sửa accountId, tenant hoặc trường cần trả | Không vượt danh sách và phạm vi do máy chủ cấp |
| View hết hạn hoặc quan hệ liên hệ bị thu hồi | Không tiếp tục đọc nhờ context cũ |
| Người yêu cầu biết tiểu sử của nạn nhân | Không được tiết lộ qua hỗ trợ chỉ bằng những dữ kiện đó |
| Kiểm tra proxy log, APM, hàng đợi và analytics | Không có bản sao không cần thiết của token hoặc liên kết định danh |
| Nhìn thấy username rồi gọi endpoint khôi phục khác | Vẫn phải đáp ứng chính sách bằng chứng riêng |
| Gửi nhiều yêu cầu chưa xác minh nhắm vào nạn nhân | Không tự khóa tài khoản hoặc thu hồi session hợp lệ |

Khi đánh giá hiệu quả chống dò, cần so sánh cả nội dung, mã HTTP, redirect, cookie, kích thước phản hồi và phân bố độ trễ trong môi trường được phép kiểm tra. Một response đơn lẻ trông giống nhau chưa đủ để kết luận không có rò rỉ.

Khôi phục tên đăng nhập cần giúp người được phép nhận đúng định danh, đồng thời giữ kín những quan hệ chưa được cấp quyền biết. Ranh giới quan trọng là từ yêu cầu công khai sang bằng chứng kiểm soát kênh, rồi từ bằng chứng đó sang tập dữ liệu được phép tiết lộ; không bước nào tự cấp quyền đăng nhập hoặc thay phương thức xác thực.
