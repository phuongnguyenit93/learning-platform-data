# Yêu cầu kênh liên hệ đã được xác minh khi khôi phục tài khoản

Trong chương **Eligibility Rules** của module **SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY**, yêu cầu **Verified contact requirement** xác định khi nào một email hoặc số điện thoại được phép tham gia luồng khôi phục tài khoản.

Một địa chỉ có định dạng đúng, nhận được thư hoặc vừa nhận được OTP chưa chắc là kênh recovery hợp lệ của tài khoản đang xét. Hệ thống cần biết kênh đó đã được liên kết với tài khoản bằng cách nào, đã xác minh giá trị nào, còn được phép sử dụng hay không và đang chứng minh điều gì.

Điểm quan trọng là tách ba kết luận:

1. **Liên kết đã được thiết lập:** kênh này thuộc cấu hình liên hệ của đúng tài khoản theo quy trình được phép.
2. **Quyền tiếp cận đã được kiểm tra:** một người đã trình được bằng chứng nhận thông điệp ở kênh đó tại thời điểm xác định.
3. **Đủ quyền thực hiện recovery:** tập bằng chứng và chính sách cho phép một hành động cụ thể như đổi mật khẩu, thay MFA hoặc đăng ký lại passkey.

Kết luận thứ hai không tự tạo ra kết luận thứ nhất hoặc thứ ba.

Bài học tập trung vào điều kiện dùng kênh liên hệ trong recovery khi mất mật khẩu, MFA, passkey hoặc thiết bị xác thực. Nó không đặt ra quy tắc rằng mọi tài khoản phải có email hoặc số điện thoại mới được recovery; một dịch vụ có thể có phương án khác, chẳng hạn bằng chứng đã đăng ký hoặc mã dự phòng, nếu chính sách cho phép.

Sau bài học, người học có thể:

- Phân biệt kênh được khai báo, kênh đã xác minh và kênh đủ điều kiện recovery.
- Thiết kế liên kết giữa tài khoản, kênh, phiên bản giá trị và bằng chứng xác minh.
- Ngăn việc thêm một địa chỉ của đối thủ ngay trong recovery rồi dùng nó để lấy tài khoản.
- Xử lý thay đổi, thu hồi, tái xác minh và mất quyền truy cập kênh liên hệ.
- Kiểm tra lại điều kiện ở lúc phát hành bằng chứng, chấp nhận bằng chứng và hoàn tất recovery.

## 1. Vì sao trường “email đã có” chưa đủ?

Giả sử An đăng ký tài khoản bằng một địa chỉ email nhưng chưa bao giờ xác nhận thư gửi đến địa chỉ đó. Dịch vụ vẫn lưu địa chỉ để hiển thị trên hồ sơ.

Sau này, An chọn “Quên mật khẩu”. Nếu hệ thống gửi token recovery tới mọi giá trị đang nằm trong trường email, nó đã coi dữ liệu người dùng từng nhập là một liên kết đã được xác minh.

Điều đó có thể dẫn tới:

- Gửi bí mật tới địa chỉ bị nhập sai.
- Cấp recovery qua một số điện thoại không còn thuộc người dùng.
- Cho phép người khác khai báo email của nạn nhân rồi tạo quan hệ tài khoản không rõ ràng.
- Sử dụng kênh chỉ dành cho thông báo như thể nó có thẩm quyền khôi phục.
- Chấp nhận một địa chỉ mới do người yêu cầu đưa vào khi chưa chứng minh quyền với tài khoản cũ.

Vấn đề không chỉ là hệ thống có gửi được thông điệp hay không. Vấn đề là **căn cứ nào cho phép thông điệp ở kênh đó tác động tới quyền của tài khoản**.

### Ba thuộc tính nên được lưu và đánh giá riêng

| Thuộc tính | Ý nghĩa | Không tự chứng minh |
|---|---|---|
| Đã khai báo | Hệ thống có một giá trị email hoặc số điện thoại | Người khai báo kiểm soát giá trị đó |
| Đã xác minh | Có bằng chứng tiếp cận đúng giá trị theo một quy trình | Người đó sẽ luôn kiểm soát kênh hoặc có mọi quyền recovery |
| Được phép dùng cho recovery | Chính sách cho phép kênh tham gia hành động đang xét | Riêng kênh đó đủ để vượt MFA hoặc passkey |

Một email nhận thông báo thanh toán có thể đã xác minh nhưng không được dùng cho recovery. Một số điện thoại liên hệ của bộ phận hỗ trợ cũng không tự trở thành yếu tố xác thực.

## 2. “Đã xác minh” thực sự có nghĩa gì?

Một cách hiểu hữu ích là:

> Hệ thống đã chấp nhận một bằng chứng cho thấy có quyền tiếp cận một giá trị liên hệ cụ thể, trong đúng ngữ cảnh, vào một thời điểm.

Ý nghĩa này phải đi cùng thông tin về quy trình và nguồn bằng chứng.

| Tín hiệu | Có thể kết luận | Không nên kết luận |
|---|---|---|
| Email có định dạng hợp lệ | Chuỗi đáp ứng quy tắc định dạng đang dùng | Hộp thư tồn tại hoặc thuộc người dùng |
| Miền nhận email có thể hoạt động | Có khả năng định tuyến thư theo kiểm tra tương ứng | Người yêu cầu kiểm soát hộp thư cụ thể |
| Nhà cung cấp báo đã phát thư hoặc SMS | Hệ thống gửi có kết quả giao nhận ở mức đó | Người nhận hợp pháp đã đọc và xác nhận |
| Trình duyệt mở liên kết bằng GET | URL đã được truy cập | Người dùng chủ động đồng ý; có thể là bộ quét |
| Token hoặc OTP được trình đúng | Người trình đã có bí mật được gửi trong phạm vi token | Họ là chủ hợp pháp của tài khoản trong mọi tình huống |
| Một nguồn danh tính khác báo kênh đã xác minh | Có một khẳng định từ nguồn đó | Nguồn được phép dùng cho recovery nếu chưa kiểm tra quan hệ tin cậy |

Với bằng chứng từ nhà cung cấp danh tính, cần xác định nguồn nào được tin, định danh nào liên kết với tài khoản cục bộ, ý nghĩa và độ mới của kết quả. Không nhận một cờ “verified” tùy ý do trình duyệt gửi lên rồi coi là sự thật.

### Xác minh kênh không phải xác minh danh tính pháp lý

Một người kiểm soát hộp thư có thể không phải người mà tên hiển thị trong hộp thư gợi ý. Một số điện thoại có thể được dùng chung hoặc được cấp lại.

Vì vậy, yêu cầu verified contact giải quyết một phần của eligibility: kênh có đủ căn cứ để được dùng trong luồng hay chưa. Nó không tự giải quyết toàn bộ bài toán xác định chủ tài khoản.

## 3. Liên kết lịch sử và quyền tiếp cận hiện tại

Một kênh đáng xem xét cho recovery cần có cả nguồn gốc liên kết và điều kiện hiện hành.

### Liên kết lịch sử đáng tin cậy

Ví dụ, người dùng đang có session được xác thực phù hợp, chủ động thêm một email recovery, xác nhận địa chỉ và hoàn tất những điều kiện thay đổi kênh mà chính sách yêu cầu.

Đây là một quá trình thiết lập liên kết. Hệ thống biết tại sao email đó được gắn với tài khoản.

Trong giai đoạn đăng ký tài khoản mới, quy trình có thể khác vì chưa có tài khoản cũ để xác thực. Tuy nhiên, xác nhận đăng ký không được âm thầm chuyển quyền một tài khoản đã tồn tại hoặc giữ lại các session không đáng tin từ một quá trình đăng ký trước đó. Xung đột với tài khoản hiện hữu phải được xử lý riêng.

### Quyền tiếp cận hiện tại

Khi recovery, hệ thống có thể gửi một challenge tới kênh đã đủ điều kiện. Kết quả thành công chứng minh người yêu cầu hiện có thể tiếp cận thông điệp đó.

Điều này không xóa bỏ các nguy cơ:

- Hộp thư bị đối thủ kiểm soát.
- Số điện thoại đã được cấp lại hoặc bị chuyển quyền ngoài ý muốn.
- Hộp thư công việc đã được gán cho nhân viên khác.
- Kênh được dùng chung hoặc có chuyển tiếp sang bên khác.
- Hai kênh nhìn khác nhau nhưng cùng phụ thuộc vào một tài khoản nền.

Một dấu thời gian xác minh từ trước không chứng minh quyền tiếp cận hiện tại. Một OTP hiện tại cũng không tự chứng minh liên kết lịch sử với tài khoản cũ.

### Cạm bẫy xác minh ngược

Luồng sau không tạo được liên kết đáng tin với tài khoản đích:

1. Người chưa xác minh chọn tài khoản cần lấy lại.
2. Họ nhập một email mới.
3. Hệ thống gửi mã tới email mới.
4. Họ nhận và nhập đúng mã.
5. Hệ thống cấp quyền recovery cho tài khoản đã chọn.

Quy trình chỉ chứng minh họ đọc được email mới. Đối thủ có thể làm mọi bước bằng hộp thư của mình.

Kênh nhận challenge recovery phải được lấy từ liên kết đủ điều kiện đã có. Nếu người dùng mất kênh cũ và cần đổi kênh, việc cho phép đổi phải dựa trên một đường xác minh khác được phê duyệt, không dựa riêng vào khả năng đọc địa chỉ mới.

## 4. Mô hình dữ liệu cần giữ được giá trị đã xác minh

Một cờ `emailVerified = true` đứng cạnh trường email có thể bị sai nghĩa sau khi giá trị email thay đổi.

Ví dụ:

~~~text
Trước thay đổi:
email = old-address
emailVerified = true

Sau một cập nhật sai:
email = new-address
emailVerified = true
~~~

Địa chỉ mới đang thừa hưởng kết quả xác minh của địa chỉ cũ.

### Gắn xác minh với bản ghi và phiên bản

Một mô hình minh họa có thể gồm:

~~~text
contact_id
account_id
tenant_id nếu hệ thống có phạm vi tổ chức
type
destination_reference
value_version
state
verified_for_version
verified_at
verification_method
verification_source
recovery_allowed
recovery_not_before
revoked_at
last_revalidated_at nếu chính sách cần
~~~

Các trường có thể được tổ chức khác nhau. Những thuộc tính quan trọng là:

- Kênh gắn với đúng tài khoản và phạm vi tổ chức.
- Kết quả xác minh chỉ áp dụng cho đúng giá trị hoặc phiên bản.
- Có trạng thái thu hồi và mục đích sử dụng.
- Có nguồn gốc, thời điểm và phương pháp xác minh khi cần giải thích.
- Có điều kiện hiệu lực bổ sung nếu chính sách yêu cầu.

Giá trị liên hệ thực tế cần được bảo vệ theo thiết kế lưu trữ của dịch vụ. Không nên đưa địa chỉ đầy đủ vào mọi log chỉ vì dữ liệu dùng để gửi thông điệp.

### Dùng phiên bản để tránh khôi phục kết quả cũ

Khi đổi từ A sang B rồi quay lại A, không nên tự nhận lại kết quả xác minh cũ chỉ vì chuỗi ký tự giống nhau. Quyền kiểm soát kênh hoặc ngữ cảnh liên kết có thể đã thay đổi.

Một challenge nên gắn với `contact_id` và `value_version`. Challenge phát hành cho phiên bản cũ không xác nhận phiên bản mới, kể cả khi giá trị hiển thị trùng nhau.

### Vai trò của chuẩn hóa và tính duy nhất

Chuẩn hóa phải nhất quán giữa đăng ký, xác minh, đăng nhập và recovery. Không tự xóa dấu chấm, hậu tố hoặc biến đổi phần địa chỉ theo quy tắc của một nhà cung cấp rồi áp dụng cho mọi email; có thể làm hai địa chỉ khác nhau bị gộp.

Số điện thoại cũng cần được phân tích theo ngữ cảnh mã quốc gia và quy tắc rõ ràng, thay vì so sánh chuỗi hiển thị tùy ý.

Việc một kênh có được gắn với nhiều tài khoản hay không là quyết định sản phẩm. Nếu cho phép, luồng recovery phải giải quyết đúng tài khoản và phạm vi quyền; nếu không cho phép, cần ràng buộc dữ liệu và xử lý cạnh tranh. Trong cả hai trường hợp, không tự chuyển liên kết từ tài khoản khác khi người dùng xác nhận một địa chỉ.

## 5. Vòng đời của kênh liên hệ

~~~mermaid
flowchart TD
    A["Khai báo hoặc đề xuất kênh"] --> B["PENDING"]
    B --> C["Xác minh đúng giá trị và ngữ cảnh"]
    C --> D["VERIFIED"]
    D --> E{"Đủ chính sách dùng cho recovery?"}
    E -->|Có| F["RECOVERY_ELIGIBLE"]
    E -->|Chưa| G["Chưa được chọn cho recovery"]
    F --> H["Kiểm tra lại khi phát hành và dùng challenge"]
    D --> I["Thay đổi, thu hồi hoặc vô hiệu"]
    F --> I
    I --> J["Không dùng kết quả cũ để cấp quyền mới"]
~~~

Tên trạng thái trong sơ đồ mang tính minh họa. Có thể triển khai bằng trạng thái cùng các thuộc tính, không cần một enum cho mỗi ô.

### Thêm kênh

Người dùng phải có thẩm quyền thêm kênh vào đúng tài khoản. Xác minh kênh mới là một điều kiện riêng, không thay cho thẩm quyền ấy.

Nếu chính sách yêu cầu xác thực lại, thời gian chờ hoặc cảnh báo qua kênh đã có, chỉ sau khi đạt những điều kiện đó kênh mới được chọn cho recovery tương ứng.

### Thay đổi kênh

Giữ địa chỉ mới ở trạng thái chờ thay vì ghi đè kênh recovery đang có rồi để nguyên cờ verified. Tại thời điểm chuyển, kiểm tra quyền thay đổi và sự nhất quán của phiên bản.

Việc thông báo tới kênh cũ giúp phát hiện thay đổi khi khả dụng. Tuy nhiên, nếu kênh cũ bị mất hoặc bị xâm nhập, bắt buộc mọi trường hợp phải xác nhận qua nó sẽ làm recovery bế tắc hoặc cho đối thủ quyền cản trở. Cần một quy trình thay thế đã được phê duyệt.

### Thu hồi hoặc nghi ngờ xâm nhập

Kênh đã thu hồi không được phát hành challenge recovery mới. Challenge còn tồn tại cần bị từ chối hoặc xử lý theo quy tắc vô hiệu tương ứng.

Nếu kênh chỉ bị đánh dấu cần xem xét, chính sách phải nói rõ được dùng cho thông báo, xác minh hay không được dùng cho hành động nào. Một trạng thái mơ hồ như “có vấn đề” dễ dẫn tới cách hiểu khác nhau giữa các endpoint.

### Tái xác minh

Có thể cần kiểm tra lại khi thay đổi giá trị, xuất hiện sự cố, có dấu hiệu kênh được gán lại hoặc quy trình yêu cầu độ mới.

Không có một thời hạn tái xác minh phù hợp cho mọi sản phẩm. Việc người dùng không mở email lâu ngày không tự chứng minh mất quyền kênh; cũng không nên coi một lần xác minh từ rất lâu là bảo đảm kiểm soát vĩnh viễn.

Tái xác minh quyền tiếp cận hiện tại không tự hợp thức hóa một liên kết đã bị thu hồi hoặc một kênh mới chưa được phép thêm.


## 6. Điều kiện chọn kênh cho một hành động recovery

Có thể diễn đạt điều kiện chọn kênh bằng một phép kết hợp:

~~~text
canUseContactForRecovery =
    linkedToTargetAccount
    AND verifiedForCurrentValueVersion
    AND activeAndNotRevoked
    AND allowedForRequestedRecoveryAction
    AND withinPolicyActivationConditions
    AND notInvalidatedByCurrentSecurityState
~~~

Đây là mô hình quyết định, không phải chỉ cần sáu cờ do phía người dùng gửi lên.

| Điều kiện | Câu hỏi cần trả lời |
|---|---|
| Đúng liên kết | Kênh thuộc tài khoản đích và đúng phạm vi tổ chức không? |
| Đúng phiên bản đã xác minh | Bằng chứng xác minh áp dụng cho giá trị hiện tại không? |
| Còn hoạt động | Kênh có bị thu hồi, thay thế hoặc đình chỉ không? |
| Đúng mục đích | Kênh được dùng cho hành động này hay chỉ nhận thông báo? |
| Đủ điều kiện kích hoạt | Có thời gian chờ hoặc điều kiện bổ sung chưa hoàn tất không? |
| Phù hợp trạng thái hiện hành | Có sự kiện xâm nhập hoặc thay đổi bảo mật làm quyết định cũ mất hiệu lực không? |

Kết quả này chỉ trả lời **có thể dùng kênh trong nhánh recovery đang xét hay không**. Sau đó, chính sách vẫn phải quyết định tập bằng chứng cần có để cấp quyền.

### Phân biệt eligibility của kênh và authorization của hành động

Một email có thể đủ điều kiện nhận token đặt lại mật khẩu, nhưng token email không được phép xóa passkey.

Một số điện thoại có thể được dùng để gửi cảnh báo, nhưng không được dùng để thay email recovery.

Một tài khoản có passkey hoặc mã dự phòng hợp lệ có thể có đường recovery không cần liên hệ qua email, nếu chính sách đã thiết kế như vậy. Không nên biến “verified contact requirement” của một nhánh thành điều kiện mới chặn mọi nhánh khác.

### Thiếu dữ liệu không đồng nghĩa đủ điều kiện

Nếu bản ghi cũ chỉ có email và một cờ không rõ nguồn, không tự suy diễn rằng email đã xác minh. Cần quy tắc chuyển đổi dữ liệu hoặc đường xác minh phù hợp, đồng thời tính tới người dùng thật có thể bị ảnh hưởng.

Khi dịch vụ kiểm tra điều kiện gặp lỗi, không mặc định cho phép gửi bí mật tới bất kỳ giá trị nào có sẵn. Có thể trì hoãn, thử lại hoặc chuyển sang phương án đã được phê duyệt mà vẫn giữ yêu cầu bảo mật.

## 7. Luồng phát hành và chấp nhận challenge đúng phạm vi

Một luồng dùng kênh đã xác minh có thể được tổ chức như sau:

1. Tiếp nhận định danh tài khoản hoặc thông tin tra cứu.
2. Giải quyết tài khoản đích theo quy tắc của dịch vụ.
3. Chọn kênh từ cấu hình đủ điều kiện phía máy chủ.
4. Tạo hồ sơ recovery và challenge ràng buộc với đúng tài khoản, kênh, phiên bản và mục đích.
5. Gửi thông điệp tới giá trị đã được chọn, không lấy một đích tùy ý từ biểu mẫu.
6. Khi nhận bằng chứng, kiểm tra lại challenge và điều kiện kênh.
7. Ghi nhận bằng chứng tiếp cận kênh vào hồ sơ.
8. Chỉ cấp quyền tiếp theo khi toàn bộ chính sách recovery được đáp ứng.

Trước khi người yêu cầu có đủ quyền xem thông tin tài khoản, phản hồi cần tránh tiết lộ tùy tiện tài khoản tồn tại, có bao nhiêu yếu tố hoặc dùng kênh nào.

### Challenge nên gắn với những gì?

~~~text
challenge_id
token_digest
account_id
recovery_attempt_id
contact_id
contact_value_version
purpose
issued_security_version
issued_at
expires_at
used_at
~~~

Token cần được sinh bằng nguồn ngẫu nhiên mật mã, đủ khó đoán cho cách sử dụng. Lưu dấu băm hoặc HMAC thay cho token thô khi phù hợp với thiết kế.

Với OTP ngắn, phải có giới hạn thử, thời hạn và phạm vi rõ; lưu dấu băm không tự làm một mã dễ đoán trở nên khó thử.

### Tách mục đích xác minh

Các mục đích sau không nên dùng lẫn nhau:

- Xác nhận kênh mới trong quá trình thêm liên hệ.
- Chứng minh tiếp cận kênh đã có trong recovery.
- Phê duyệt thay kênh recovery.
- Thực hiện thay đổi credential hoặc cấp session.

Một token dùng để xác nhận email đăng ký không tự có quyền reset mật khẩu của một tài khoản khác có cùng địa chỉ hiển thị.

Tương tự, token recovery không nên tự đưa một kênh bị thu hồi trở lại trạng thái hoạt động. Đó là một thay đổi cấu hình bảo mật, cần thẩm quyền riêng.

### Không chỉ kiểm tra khi gửi

Giữa lúc phát hành challenge và lúc sử dụng, kênh có thể bị thay hoặc thu hồi. Vì vậy, kết quả eligibility lúc phát hành không đủ để chấp nhận mọi token về sau.

Nếu thông điệp đi qua hàng đợi gửi, worker cũng cần xử lý đúng phiên bản và trạng thái hiện hành trước khi gửi theo thiết kế. Dù đã gửi hoặc thư cũ đến trễ, endpoint nhận token vẫn phải từ chối challenge đã mất hiệu lực.

Không thể thu hồi một email đã tới hộp thư, nhưng có thể và cần vô hiệu quyền của token trong email đó.

## 8. Mã giả kiểm tra bằng chứng tiếp cận kênh

Đoạn mã sau minh họa nhánh recovery qua kênh đã đủ điều kiện. Nó không dùng để xác minh kênh mới trong trạng thái đăng ký chờ.

~~~text
function acceptRecoveryContactProof(rawToken, recoveryContext):
    digest = digestToken(rawToken)

    transaction:
        records = lockRelatedRecordsInConsistentOrder(digest)
        challenge = records.challenge
        attempt = records.attempt
        account = records.account
        contact = records.contact

        require challenge exists
        require challenge.purpose == "RECOVERY_CONTACT_PROOF"
        require challenge.usedAt is null
        require now < challenge.expiresAt

        require recoveryContext is authorized for attempt
        require attempt is active
        require attempt.accountId == account.id
        require challenge.accountId == account.id
        require challenge.recoveryAttemptId == attempt.id

        require contact.accountId == account.id
        require contact.id == challenge.contactId
        require contact.valueVersion == challenge.contactValueVersion
        require contact.verifiedForVersion == contact.valueVersion
        require account.securityVersion == challenge.issuedSecurityVersion

        require contactIsEligible(
            account,
            contact,
            attempt.requestedActions,
            currentPolicy
        )

        challenge.usedAt = now
        recordContactPossessionProof(
            attempt,
            contact.id,
            contact.valueVersion,
            now,
            challenge.id
        )

    return limitedRecoveryContext(attempt.id)
~~~

Những điểm cần giữ:

- Kiểm tra và tiêu thụ token dùng một lần phải xử lý cạnh tranh an toàn.
- Các ràng buộc tài khoản, hồ sơ và phiên bản phải được kiểm tra phía máy chủ.
- Một bằng chứng thành công chỉ được gắn vào đúng hồ sơ.
- Kết quả không tự là session tài khoản đầy đủ.
- Kiểm tra cuối trước khi đổi credential vẫn phải đánh giá toàn bộ điều kiện hiện hành.

Nếu hệ thống ghi nhận bằng chứng rồi mất kết nối trước khi trả phản hồi, tiếp tục bằng checkpoint và context phù hợp. Không bật token đã dùng trở lại để giải quyết lỗi giao diện.

Nếu dùng phiên bản bảo mật để vô hiệu challenge, cần định nghĩa những thay đổi nào làm tăng phiên bản và xử lý hồ sơ bị ảnh hưởng. Không chỉ thêm một trường phiên bản mà các đường thay đổi kênh hoặc credential không cập nhật nó.

## 9. Các trường hợp dễ bị gắn nhãn verified sai

### Địa chỉ đã xác minh được sửa trực tiếp

Một endpoint cập nhật hồ sơ đổi email nhưng không xóa hoặc thay phạm vi xác minh. Kết quả là địa chỉ mới thừa hưởng cờ của địa chỉ cũ.

Cách tránh là quản lý kênh mới ở trạng thái chờ, ràng buộc xác minh với phiên bản và chỉ kích hoạt sau đúng quy trình.

### Xác nhận một địa chỉ cho nhiều tài khoản không kiểm soát

Một token được tạo cho tài khoản A, nhưng endpoint chỉ tìm email rồi đánh dấu verified cho mọi tài khoản có email ấy.

Bằng chứng cần gắn với đúng quan hệ tài khoản–kênh. Việc cùng giá trị liên hệ xuất hiện ở nhiều nơi không cho phép một token tác động tới tất cả.

### Nhập lại cùng một số đã bị thu hồi

Một số điện thoại bị loại vì nghi xâm nhập. Người chưa được xác minh nhập lại số đó và nhận OTP, rồi hệ thống khôi phục quyền recovery ngay.

Đây là nhầm lẫn giữa tiếp cận hiện tại với quyền thay đổi cấu hình. Việc tái liên kết phải có căn cứ được phép, không chỉ có OTP.

### Đồng bộ cờ từ nguồn không đáng tin

Một công cụ nhập dữ liệu, API quản trị hoặc tích hợp ngoài gửi cờ verified mà không có hợp đồng tin cậy hoặc bằng chứng tương ứng.

Cần kiểm soát nguồn, quyền ghi và ý nghĩa của cờ. Sửa dữ liệu hành chính không được tự cấp một kênh recovery mới.

### Địa chỉ công việc hoặc hộp thư dùng chung

Địa chỉ có thể được chuyển cho người khác sau khi nhân sự thay đổi. Hộp thư bộ phận có thể được nhiều người đọc.

Nếu dịch vụ cho phép dùng chúng, phải xác định mô hình quyền: tài khoản thuộc cá nhân hay tổ chức, ai được ủy nhiệm và điều gì xảy ra khi quyền kênh thay đổi. Kiểm soát một miền email không tự chứng minh quyền cá nhân với mọi tài khoản dùng miền đó.

### Số điện thoại được cấp lại

Một số từng xác minh có thể thuộc người khác ở thời điểm sau. OTP hiện tại chứng minh tiếp cận số hiện tại, không chứng minh người nhận là chủ tài khoản trong lịch sử.

Cần đánh giá theo rủi ro, bằng chứng bổ sung và cơ chế thay hoặc ngừng dùng kênh. Không thể giải quyết mọi trường hợp chỉ bằng việc gửi thêm một SMS.

### Kênh mới vừa được thêm sau một session bị đánh cắp

Ngay cả khi người thêm kênh có session hợp lệ về mặt kỹ thuật, session đó có thể không đủ bảo đảm cho thay đổi nhạy cảm. Chính sách cần quy định khi nào phải xác thực lại hoặc dùng bằng chứng khác trước khi cho phép thêm kênh recovery.

Xác nhận kênh mới chỉ chứng minh người đó kiểm soát kênh mới, không sửa được việc thẩm quyền thêm kênh vốn chưa đủ.

## 10. Khi người dùng không còn kênh đã xác minh

Một người dùng thật có thể mất email, mất số điện thoại hoặc thiết bị nhận mã. Yêu cầu verified contact không nên được biến thành một vòng lặp vô ích: “muốn đổi email thì phải nhận mã qua email đã mất”.

Thay vào đó, cần xem các đường đã được chính sách thiết lập:

| Tài sản hoặc quyền còn lại | Có thể hỗ trợ thế nào? | Điều kiện |
|---|---|---|
| Passkey đã đăng ký | Xác thực để thực hiện nhánh thay kênh hoặc recovery tương ứng | Kiểm tra đúng yêu cầu và phạm vi hành động |
| Mã dự phòng hợp lệ, giữ riêng | Cung cấp bằng chứng sở hữu theo chính sách | Dùng một lần; không mặc định an toàn nếu đã lộ cùng email |
| Một kênh độc lập khác đã đủ điều kiện | Nhận challenge theo nhánh được phép | Đánh giá tính độc lập và mức bảo đảm |
| Session hiện có | Có thể hỗ trợ chuyển tiếp hoặc xác thực lại | Session phải đủ điều kiện; không chỉ dựa vào cookie |
| Quyền quản trị tổ chức đã thiết lập | Có thể xử lý theo mô hình tài khoản thuộc tổ chức | Xác minh đúng thẩm quyền và ghi rõ cơ sở cấp quyền |
| Quy trình xác minh tăng cường phù hợp | Xem xét khi dịch vụ có dữ liệu và năng lực liên kết đáng tin cậy | Không thu thập tài liệu vô ích hoặc hứa chắc sẽ recovery |

Nếu không có bất kỳ đường đủ tin cậy nào, có thể phải chưa cấp lại quyền. Đây là giới hạn thực tế, không phải vấn đề có thể sửa bằng việc cho người yêu cầu tự chọn email mới.

Không phải dịch vụ nào cũng đã biết danh tính pháp lý của người dùng. Một giấy tờ mới được cung cấp chưa chắc liên kết được với tài khoản cũ. Chỉ tăng lượng tài liệu thu thập không tự làm bằng chứng mạnh hơn.

### Sau khi đủ điều kiện đổi kênh

Quy trình có thể gồm:

1. Xác minh thẩm quyền thay đổi bằng đường phù hợp.
2. Đưa kênh mới vào trạng thái chờ.
3. Xác minh quyền tiếp cận đúng giá trị mới.
4. Áp dụng thời gian chờ hoặc hạn chế nếu chính sách yêu cầu.
5. Kích hoạt phạm vi recovery được phép.
6. Xử lý challenge cũ, session và cảnh báo theo kế hoạch.
7. Ghi lại cơ sở liên kết mới mà không lưu bí mật thô.

Không được cho bước xác minh kênh mới tự thay thế bước đầu tiên.

## 11. Verified contact không có nghĩa là bằng chứng độc lập hoặc đủ mạnh

Giả sử tài khoản dùng email làm recovery và gửi thêm một OTP tới cùng hộp thư khi người dùng mất passkey. Cả email lẫn OTP đều hợp lệ, nhưng vẫn chỉ dựa vào một miền kiểm soát.

Nếu hộp thư bị xâm nhập, đối thủ có thể hoàn thành cả hai.

Tương tự:

- Hai alias cùng chuyển về một hộp thư không tạo hai kênh độc lập.
- Mã dự phòng lưu trong email không độc lập với sự cố email.
- Kênh thứ hai được khôi phục qua kênh thứ nhất có thể cùng nằm trong phạm vi sự cố.
- Passkey mới được đăng ký trong một context recovery yếu không chứng minh quyền sở hữu trước đó.

Chính sách cần xem mức bảo đảm của toàn bộ tập bằng chứng, không chỉ đếm số kênh có nhãn verified.

### Trường hợp sản phẩm chấp nhận email là gốc tin cậy

Một số dịch vụ chủ động cho phép recovery chỉ qua email đã liên kết và xác minh. Trong mô hình đó, chiếm hộp thư có thể kéo theo chiếm tài khoản.

Thiết kế token tốt vẫn cần thiết để chống đoán, phát lại và lộ token ngoài ý muốn. Nhưng nó không loại bỏ rủi ro từ việc gửi đúng bí mật vào hộp thư của đối thủ.

Tài liệu và trải nghiệm cần phản ánh đúng mức bảo đảm. Không được gọi một luồng email-only là đã bảo vệ được trước mọi trường hợp hộp thư bị xâm nhập.

## 12. Chống lạm dụng và bảo vệ thông tin liên hệ

### Gửi mã và thử mã

Cần giới hạn việc tạo yêu cầu, gửi lại, thử OTP và chọn kênh. Có thể kết hợp tài khoản, kênh, hồ sơ và nguồn yêu cầu.

Giới hạn chỉ theo tài khoản có thể bị dùng để ngăn nạn nhân recovery. Giới hạn chỉ theo IP có thể ảnh hưởng người dùng chung mạng hoặc bị né. Cần đánh giá tác động từ chối dịch vụ và có cách xử lý người dùng hợp lệ.

Không cho người chưa xác minh thay phiên gửi mã tới một danh sách địa chỉ tùy ý dưới danh nghĩa một tài khoản đích.

### Thông tin hiển thị

Một danh sách email hoặc số điện thoại recovery đầy đủ có thể tiết lộ dữ liệu cá nhân. Trước khi có quyền phù hợp, phản hồi nên tối thiểu và nhất quán theo thiết kế chống dò tài khoản.

Hiển thị một phần giá trị cũng có thể làm lộ thông tin khi kết hợp với dữ liệu khác. Chỉ hiển thị gợi ý khi thật sự cần và phù hợp với trạng thái xác minh của người xem.

Thông báo “đã gửi nếu thông tin đủ điều kiện” có thể giúp hạn chế tiết lộ ở điểm khởi tạo. Nhưng thông báo chung không thay thế kiểm tra eligibility phía máy chủ.

### Token, URL và nhật ký

Không ghi token, OTP, mã dự phòng hoặc URL chứa bí mật vào log. Trang xử lý token nên tránh tài nguyên bên thứ ba và kiểm soát việc lộ qua referrer hoặc công cụ phân tích.

Không dùng một yêu cầu GET để hoàn tất recovery hoặc thay đổi credential. Bộ quét email có thể truy cập URL tự động; thao tác chấp nhận bằng chứng và thay đổi trạng thái cần được thiết kế với hành động xác nhận phù hợp, bao gồm bảo vệ chống giả mạo yêu cầu theo ngữ cảnh.

Nhật ký nên chứa mã tài khoản, mã kênh, phiên bản, mục đích và mã lý do. Giá trị liên hệ đầy đủ chỉ nên xuất hiện ở nơi cần thiết với quyền truy cập tương ứng.

## 13. Tình huống kiểm tra thiết kế

Bảng sau là các tình huống rà soát cho bài học, không phải kết quả kiểm thử của một hệ thống cụ thể.

| Tình huống | Kết quả mong đợi |
|---|---|
| Email có trong hồ sơ nhưng chưa xác minh | Không tự đủ điều kiện cho nhánh yêu cầu verified contact |
| Nhà cung cấp báo thư đã phát | Không tự đánh dấu đã xác minh chỉ từ delivery status |
| Người yêu cầu nhập email mới khi bắt đầu recovery tài khoản cũ | Không dùng việc nhận mã ở email mới làm căn cứ chuyển quyền |
| Email được sửa nhưng cờ verified cũ vẫn còn | Phiên bản và quy trình cập nhật ngăn kế thừa xác minh sai |
| Token cho kênh phiên bản cũ được trình sau thay đổi | Bị từ chối theo ràng buộc phiên bản hoặc cơ chế vô hiệu |
| Đổi A sang B rồi trở lại A | Không tự hồi sinh challenge hoặc kết quả xác minh cũ |
| Cùng địa chỉ xuất hiện ở hai tài khoản | Token chỉ tác động tới đúng quan hệ tài khoản–kênh |
| Token xác minh đăng ký được gửi tới endpoint recovery | Bị từ chối vì sai mục đích hoặc phạm vi |
| Kênh bị thu hồi sau khi đã phát hành token | Token không tiếp tục cấp quyền trái trạng thái hiện hành |
| Thư trong hàng đợi đến sau khi kênh thay đổi | Endpoint vẫn từ chối token mất hiệu lực |
| Hai yêu cầu cùng dùng một token | Chỉ một lần tiêu thụ thành công |
| Bộ quét mở liên kết | Không hoàn tất recovery hoặc đổi credential bằng GET |
| Người dùng mất kênh nhưng còn bằng chứng độc lập được phép | Có nhánh recovery hoặc thay kênh phù hợp, không bắt nhận mã ở kênh đã mất |
| Chỉ còn email bị nghi xâm nhập | Không coi nhiều mã qua cùng email là bằng chứng độc lập |
| Tài khoản không có verified contact nhưng có đường recovery khác được phép | Không áp đặt yêu cầu email ngoài phạm vi chính sách của nhánh đó |
| API hoặc công cụ nhập liệu tự đặt verified | Chỉ nguồn và người có quyền đúng phạm vi mới được tạo kết quả tương ứng |

## 14. Ví dụ xuyên suốt: thêm kênh mới và recovery sau đó

Bình đang sử dụng tài khoản có passkey. Anh muốn thêm một email recovery mới.

Một trình tự phù hợp có thể là:

1. Bình chứng minh thẩm quyền thay đổi theo chính sách của tài khoản.
2. Dịch vụ tạo bản ghi liên hệ mới ở trạng thái chờ với phiên bản xác định.
3. Challenge xác minh được ràng buộc với tài khoản, bản ghi và đúng phiên bản.
4. Bình trình bằng chứng nhận thông điệp; dịch vụ ghi kết quả xác minh.
5. Sau các điều kiện kích hoạt cần thiết, kênh được phép dùng cho những hành động recovery đã quy định.
6. Khi Bình mất thiết bị, hệ thống chọn kênh từ cấu hình này, không lấy một địa chỉ mới tùy ý từ biểu mẫu.
7. Bằng chứng tiếp cận email được ghi vào hồ sơ, nhưng việc thay passkey và cấp session vẫn cần toàn bộ điều kiện recovery tương ứng.
8. Nếu email bị thu hồi hoặc thay đổi trong lúc hồ sơ đang chạy, các quyết định liên quan được kiểm tra lại trước khi cấp quyền.

Nếu một người khác chỉ biết tên tài khoản của Bình và nhập email của họ, việc họ nhận được mã ở email ấy không cho phép họ thực hiện chuỗi trên.

Yêu cầu kênh liên hệ đã xác minh chỉ có ý nghĩa khi giữ được cả **nguồn gốc liên kết, đúng giá trị đã xác minh và phạm vi quyền hiện hành**. Một cờ verified đơn lẻ không thay thế ba điều đó.
