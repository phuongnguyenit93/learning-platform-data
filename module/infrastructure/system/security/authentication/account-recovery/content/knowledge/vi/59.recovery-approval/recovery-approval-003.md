# Approval evidence review — Thẩm định bằng chứng trước khi phê duyệt khôi phục

## 1. Phê duyệt phải trả lời được câu hỏi nào?

Trong một luồng khôi phục tài khoản, người yêu cầu thường không thể sử dụng phương thức đăng nhập bình thường: quên mật khẩu, mất điện thoại chứa MFA, không còn passkey hoặc mất thiết bị xác thực. Quản trị viên có thể được giao quyền phê duyệt để người dùng tiếp cận một đường khôi phục khác. Quyền đó có giá trị cao vì kẻ tấn công cũng có thể sử dụng cùng một câu chuyện để xin thay đổi yếu tố xác thực của nạn nhân.

**Approval evidence review** là quá trình thẩm định các bằng chứng dùng làm căn cứ phê duyệt. Mục tiêu không phải là xác nhận hồ sơ đã đính kèm đủ tệp, mà là xác định những bằng chứng đó thực sự chứng minh điều gì, còn đáng tin cậy đến đâu và có đủ để cho phép đúng hành động được yêu cầu hay không.

Một người duyệt cần trả lời ba câu hỏi riêng biệt:

1. Người yêu cầu có liên hệ đáng tin cậy nào với tài khoản cần khôi phục?
2. Người đó có đủ thẩm quyền thực hiện hành động đang đề nghị?
3. Với bằng chứng và rủi ro hiện tại, hệ thống có thể cho phép hành động này theo chính sách không?

Đối với `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, câu trả lời phải kết nối được việc xác minh danh tính với đánh giá rủi ro, chống lạm dụng, quyền khôi phục dùng một lần và kiểm soát phiên. Thẩm định bằng chứng là đầu vào cho quyết định bảo mật, không tự thay thế các lớp kiểm soát còn lại.

### Ví dụ xuyên suốt

Một người liên hệ bộ phận hỗ trợ, khai rằng họ là chủ tài khoản `account-742` và đã mất điện thoại MFA. Người đó cung cấp ảnh chụp hóa đơn, tên công ty và một địa chỉ email mới để nhận liên kết khôi phục.

Hóa đơn có thể cho thấy người gửi biết một giao dịch. Tên công ty có thể là thông tin công khai. Địa chỉ email mới chỉ là nơi người gửi muốn nhận kết quả. Nếu không có kiểm tra bổ sung, tập thông tin này chưa chứng minh rằng người gửi được quyền thay yếu tố MFA của `account-742`.

Người duyệt phải phân biệt dữ liệu **do người yêu cầu khai báo** với kết quả **được xác minh từ nguồn có thẩm quyền**, rồi xem các kết quả đó có phù hợp với chính sách áp dụng cho hành động đăng ký lại MFA hay không.

## 2. Tách yêu cầu chứng minh, vật chứng và kết quả xác minh

Một mô hình hữu ích gồm bốn lớp:

| Lớp | Nội dung | Ví dụ |
|---|---|---|
| Yêu cầu chứng minh | Điều cần xác lập để được đi tiếp | Người yêu cầu kiểm soát một kênh đã gắn với tài khoản từ trước |
| Vật chứng hoặc tín hiệu | Dữ liệu được thu thập | Thử thách gửi đến kênh đã đăng ký, tệp đính kèm, hồ sơ tổ chức |
| Kết quả xác minh | Điều hệ thống hoặc người có thẩm quyền đã kiểm tra | Thử thách được hoàn thành trong ngữ cảnh yêu cầu hiện tại |
| Kết luận thẩm định | Mức độ kết quả đáp ứng chính sách | Đáp ứng một điều kiện, nhưng chưa đủ để bỏ MFA |

Một ảnh chụp màn hình có dòng “xác minh thành công” không tương đương kết quả xác minh được backend ghi nhận. Tương tự, sự tồn tại của tệp giấy tờ không đồng nghĩa giấy tờ đã được kiểm tra nguồn gốc, tính phù hợp hoặc mối liên hệ với tài khoản.

Người duyệt cần ghi được cả kết luận và giới hạn của từng bằng chứng. Ví dụ: “Hoàn tất thử thách trên kênh email đã đăng ký” chỉ chứng minh khả năng tiếp cận kênh đó trong bối cảnh xác minh; nó không tự chứng minh kênh email chưa bị chiếm đoạt hoặc người thực hiện là chủ thể hợp pháp của mọi tài khoản liên quan.

Không gọi toàn bộ hồ sơ là `verified = true` nếu các thành phần chỉ xác lập được những thuộc tính khác nhau. Việc giữ rõ ý nghĩa từng kết quả giúp tránh mở rộng kết luận vượt quá điều đã kiểm tra.

## 3. Định nghĩa trước chính sách cần đáp ứng

Nếu người duyệt phải tự nghĩ ra tiêu chí sau khi đọc một câu chuyện thuyết phục, kết quả sẽ phụ thuộc nhiều vào áp lực hỗ trợ và kinh nghiệm cá nhân. Hệ thống nên xác định chính sách trước theo loại tài khoản, loại hành động và mức rủi ro.

Chính sách cần mô tả:

- Những điều kiện bắt buộc để yêu cầu được xét duyệt.
- Các loại bằng chứng được chấp nhận và điều mà từng loại có thể chứng minh.
- Giới hạn về độ mới, nguồn xác minh và sự độc lập giữa các bằng chứng.
- Những dấu hiệu buộc phải tạm giữ, từ chối hoặc chuyển sang người có thẩm quyền cao hơn.
- Phạm vi hành động có thể được cấp khi các điều kiện được đáp ứng.
- Yêu cầu phân tách nhiệm vụ hoặc nhiều người duyệt cho hành động nhạy cảm.

Ví dụ minh họa: một tài khoản đặc quyền mất toàn bộ yếu tố xác thực có thể cần quy trình khác với một tài khoản thông thường vẫn còn yếu tố dự phòng đáng tin cậy. Đây là lựa chọn thiết kế theo rủi ro, không phải một bộ tiêu chuẩn số lượng bằng chứng cố định áp dụng cho mọi hệ thống.

Một điểm rủi ro thấp không được tự bù cho điều kiện bắt buộc còn thiếu. Nếu chính sách đòi hỏi một kết quả xác minh độc lập, năm tệp do cùng người yêu cầu gửi không tự thay thế được kết quả đó.

## 4. Các chiều cần xem xét trên từng bằng chứng

### 4.1. Nguồn gốc và đường thu thập

Cần biết bằng chứng xuất phát từ đâu, ai thu thập, qua kênh nào và có thể đối chiếu với nguồn nào. Dữ liệu lấy trực tiếp từ một hệ thống nội bộ có kiểm soát khác với bản chụp dữ liệu mà người gửi tự cung cấp.

Nếu cần xác nhận từ một quản trị viên tổ chức, danh tính và thẩm quyền của người xác nhận phải được kiểm tra qua hồ sơ tổ chức đã có hoặc một quy trình được phê duyệt. Không gọi đến số điện thoại mà chính người xin khôi phục vừa cung cấp rồi xem lời xác nhận nhận được là độc lập.

### 4.2. Tính toàn vẹn

Hệ thống cần phát hiện việc thay đổi vật chứng sau khi nó đã được thu thập hoặc duyệt. Có thể dùng phiên bản, định danh bất biến và giá trị băm để ràng buộc kết quả thẩm định với đúng dữ liệu đã xem.

Giá trị băm chỉ giúp phát hiện sự khác nhau của nội dung so với một bản tham chiếu. Nó không chứng minh nội dung ban đầu là thật. Một tài liệu giả vẫn có thể được lưu trữ nguyên vẹn và có giá trị băm hợp lệ.

### 4.3. Độ mới

Bằng chứng có thể đúng vào thời điểm thu thập nhưng không còn đủ phù hợp tại thời điểm phê duyệt. Cần phân biệt thời điểm xảy ra sự kiện, thời điểm thu thập và thời điểm hoàn tất xác minh.

Ví dụ, một thử thách đã hoàn tất từ một yêu cầu khôi phục cũ không mặc nhiên áp dụng cho yêu cầu mới. Bằng chứng cần nằm trong khoảng thời gian được chính sách chấp nhận và còn đúng với ngữ cảnh đang duyệt.

### 4.4. Ràng buộc với tài khoản và hành động

Bằng chứng phải liên hệ được với đúng tenant, tài khoản, yêu cầu và nội dung hành động. Việc chứng minh một người đang làm việc tại công ty không tự cho phép họ khôi phục tài khoản của mọi đồng nghiệp trong tenant đó.

Nếu đích nhận kết quả hoặc yếu tố cần thay đổi được sửa sau khi thu thập bằng chứng, cần xem việc sửa đó có làm mất hiệu lực kết quả thẩm định hay không. Những thay đổi ảnh hưởng đến quyền được cấp phải tạo phiên bản yêu cầu mới hoặc khiến lượt duyệt trước không còn được sử dụng.

### 4.5. Tính độc lập

Hai bằng chứng chỉ hữu ích như hai nguồn độc lập khi chúng không cùng thất bại theo một nguyên nhân chung quan trọng. Email xác nhận và tài liệu nằm trong cùng một hộp thư có thể cùng bị kẻ chiếm hộp thư lấy được.

Một mã gửi qua kênh vừa được người yêu cầu thay đổi cũng không trở thành bằng chứng độc lập cho quyền thay đổi kênh đó. Đây là vòng lặp tin cậy: hệ thống dùng chính kết quả đang xin phê duyệt để chứng minh rằng việc phê duyệt là hợp lệ.

### 4.6. Dấu hiệu mâu thuẫn hoặc bị lạm dụng

Bằng chứng cần được xem cùng các tín hiệu bất lợi như nhiều yêu cầu liên tiếp, thay đổi kênh liên hệ gần đây, tài khoản đang có cảnh báo hoặc câu chuyện thay đổi qua các lần liên hệ. Một tín hiệu bất thường không tự chứng minh gian lận, nhưng không nên bị bỏ qua chỉ vì hồ sơ có đủ số lượng tệp.

## 5. Bằng chứng nào thường dễ bị hiểu quá mức?

| Loại thông tin | Có thể hỗ trợ điều gì? | Giới hạn cần ghi nhận |
|---|---|---|
| Tên, ngày sinh, địa chỉ, tên công ty | Đối chiếu hồ sơ hoặc phát hiện bất nhất | Có thể công khai, bị rò rỉ hoặc được người khác biết |
| Hóa đơn hoặc lịch sử giao dịch | Hỗ trợ liên hệ với một giao dịch | Có thể bị chia sẻ; biết giao dịch không tự chứng minh quyền đổi yếu tố xác thực |
| Ảnh chụp giao diện tài khoản | Cung cấp thông tin để điều tra | Có thể cũ hoặc bị chỉnh sửa; không thay thế dữ liệu backend |
| Thử thách trên kênh đã đăng ký | Chứng minh khả năng tiếp cận kênh tại một thời điểm | Kênh có thể đang bị chiếm đoạt; cần xét mô hình đe dọa |
| Yếu tố dự phòng đã được thiết lập trước | Có thể cung cấp căn cứ mạnh hơn theo chính sách | Phải xác minh qua luồng chính thức, chống replay và kiểm tra trạng thái thu hồi |
| Xác nhận của tổ chức | Hỗ trợ xác lập vai trò hoặc quyền đại diện | Cần xác minh người xác nhận và phạm vi thẩm quyền từ nguồn đáng tin cậy |
| Giấy tờ nhận dạng | Có thể hỗ trợ một quy trình xác minh danh tính được thiết kế phù hợp | Không tự gắn người cầm giấy tờ với tài khoản; ảnh giấy tờ có thể bị đánh cắp hoặc giả mạo |
| Lịch sử phiên và thiết bị | Hỗ trợ đánh giá tính liên tục hoặc bất thường | Tín hiệu thiết bị có thể thay đổi, bị sao chép hoặc đến từ phiên bị chiếm đoạt |

Không yêu cầu người dùng gửi mật khẩu hiện tại, mã OTP đang hoạt động, recovery code hoặc bí mật MFA qua chat hỗ trợ để làm bằng chứng. Nếu chính sách cho phép sử dụng một yếu tố dự phòng, người dùng cần thực hiện trong luồng xác minh chính thức; hệ thống ghi nhận kết quả thay vì để người hỗ trợ đọc bí mật.

Đối với tài khoản chưa từng được gắn với danh tính pháp lý, việc nhận được giấy tờ của một người có tên tương tự không tự tạo ra mối liên hệ đáng tin cậy với tài khoản. Người duyệt phải dựa vào căn cứ mà hệ thống thực sự thiết lập được, thay vì suy diễn rằng mọi tài khoản đều có một danh tính ngoài đời đã được xác minh từ trước.

## 6. Hồ sơ thẩm định cần chứa những gì?

Một hồ sơ có cấu trúc giúp người duyệt thấy được căn cứ và giúp backend ràng buộc quyết định với đúng phiên bản dữ liệu.

```text
reviewId
tenantId
accountId
recoveryRequestId
requestVersion
requestedAction
actionPayloadDigest
evidenceSetId
evidenceSetVersion
policyVersion
reviewerId
reviewStartedAt
reviewCompletedAt
outcome
reasonCodes
approvedScope
```

Mỗi mục bằng chứng có thể ghi nhận:

```text
evidenceId
evidenceType
sourceReference
sourceTrustDomain
collectedAt
verifiedAt
usableUntil
verificationMethod
verificationOutcome
verifierReference
integrityReference
limitations
```

Những trường này là mô hình minh họa, không phải yêu cầu lưu mọi dữ liệu thô vào cùng bảng. Tài liệu gốc và kết quả xác minh nên có vùng lưu trữ, quyền đọc và thời gian lưu phù hợp với độ nhạy cảm của từng loại.

`sourceTrustDomain` giúp người duyệt phát hiện các mục có chung nguồn thất bại, nhưng không tự chứng minh tính độc lập. Việc gắn nhãn “email” và “tài liệu” thành hai loại khác nhau không làm chúng độc lập nếu tài liệu được lấy từ chính hộp thư đó.

`limitations` cần nói rõ điều chưa được chứng minh. Ví dụ: “Xác nhận người yêu cầu còn là nhân viên, chưa xác nhận quyền quản trị tenant.” Ghi rõ giới hạn tốt hơn một nhãn “PASS” không giải thích.

## 7. Quy trình thẩm định từ đầu đến quyết định

### Bước 1: Xác nhận phạm vi và người có quyền duyệt

Người duyệt truy cập hồ sơ qua công cụ nội bộ được kiểm soát, kiểm tra tenant, tài khoản và hành động đề nghị. Hệ thống kiểm tra người duyệt có thẩm quyền phù hợp và không vi phạm quy tắc tự duyệt hoặc xung đột lợi ích.

Người dùng có thể đủ điều kiện yêu cầu khôi phục tài khoản cá nhân nhưng không đủ thẩm quyền thay đổi chủ sở hữu một tài khoản tổ chức. Phạm vi hành động phải được xác định trước khi đánh giá bằng chứng.

### Bước 2: Cố định phiên bản hồ sơ được xem xét

Tạo hoặc sử dụng một phiên bản tập bằng chứng có định danh rõ ràng. Người duyệt cần biết mình đang xem dữ liệu nào. Nếu có bằng chứng mới hoặc nội dung hành động thay đổi trong lúc duyệt, hệ thống phải báo thay đổi và không âm thầm áp dụng kết luận cũ vào bộ hồ sơ mới.

### Bước 3: Kiểm tra từng kết quả xác minh

Đối chiếu phương pháp, nguồn, thời điểm và trạng thái của bằng chứng. Nếu một dịch vụ xác minh trả kết quả chưa hoàn tất, không chuyển nó thành thành công vì người duyệt cần giải quyết nhanh.

Việc chưa xác minh được và việc xác minh thất bại là hai trạng thái khác nhau. Mất kết nối tới dịch vụ không chứng minh người dùng gian lận, nhưng cũng không cung cấp bằng chứng cần thiết để duyệt.

### Bước 4: Xem xét toàn bộ tập bằng chứng

Kiểm tra độ bao phủ các điều kiện bắt buộc, mối phụ thuộc giữa các bằng chứng và các mâu thuẫn chưa được giải thích. Không chỉ đọc mục có kết quả thuận lợi nhất.

Ví dụ, thử thách email hoàn tất thành công nhưng email đó vừa được thay trong một phiên đáng ngờ. Người duyệt cần xem kênh này có còn được phép làm căn cứ theo chính sách không, thay vì tự coi kết quả thử thách là đủ.

### Bước 5: Kết hợp với rủi ro hiện tại

Kiểm tra yêu cầu còn đang ở trạng thái cho phép xử lý, các tín hiệu rủi ro có thay đổi và có cảnh báo ngăn phê duyệt hay không. Kết quả thẩm định bằng chứng có thể hợp lệ về mặt dữ liệu nhưng hành động vẫn phải bị tạm giữ nếu tài khoản đang trong một sự cố cần điều tra.

### Bước 6: Ra quyết định có lý do và phạm vi

Ghi nhận kết quả, mã nguyên nhân và điều kiện áp dụng. Nếu chấp thuận, chỉ cấp phạm vi cần thiết: ví dụ quyền đi vào luồng đăng ký lại MFA, thay vì vô hiệu hóa mọi biện pháp bảo vệ hoặc đăng nhập trực tiếp với đầy đủ đặc quyền.

Phê duyệt cần được gắn với phiên bản hồ sơ đã xét và có thời hạn theo chính sách. Backend vẫn phải kiểm tra các điều kiện hiện tại khi quyền khôi phục được sử dụng.

## 8. Xử lý thiếu bằng chứng, mâu thuẫn và nghi ngờ giả mạo

Không nên ép mọi tình huống thành hai nút “duyệt” hoặc “từ chối”. Một tập trạng thái có thể gồm:

| Kết quả | Ý nghĩa | Hướng tiếp theo |
|---|---|---|
| Cần bổ sung | Thiếu điều kiện có thể hoàn thiện qua luồng được phép | Yêu cầu đúng loại thông tin còn thiếu |
| Chờ xác minh | Kết quả xác minh chưa sẵn sàng hoặc chưa đủ mới | Thực hiện lại bước cần thiết, giữ nguyên giới hạn quyền |
| Cần điều tra | Có mâu thuẫn trọng yếu hoặc dấu hiệu bị lạm dụng | Chuyển đến bộ phận có thẩm quyền theo quy trình |
| Từ chối | Không đáp ứng chính sách cho hành động đề nghị | Ghi nguyên nhân nội bộ và thông báo phù hợp |
| Chấp thuận có phạm vi | Đủ căn cứ cho một hành động cụ thể | Tạo quyết định giới hạn và kiểm soát sử dụng |

Mâu thuẫn cần được xử lý theo tính chất. Sai khác tên do thay đổi hợp pháp không giống một kết quả xác minh nguồn bị chỉnh sửa. Chính sách cần cho phép bổ sung hoặc xác minh theo cách phù hợp, thay vì tự động suy luận gian lận từ mọi khác biệt.

Ngược lại, người duyệt không nên “chọn tin” một bằng chứng thuận lợi để bỏ qua mâu thuẫn trọng yếu. Nếu chưa thể giải thích một thay đổi kênh nhận kết quả hoặc xác nhận tổ chức không hợp lệ, giữ yêu cầu ở trạng thái chưa được cấp quyền là kết quả hợp lý.

Thông báo cho người yêu cầu có thể nêu bước tiếp theo, nhưng không nên tiết lộ chi tiết cơ chế phát hiện gian lận hoặc trả lời câu hỏi có thể làm lộ sự tồn tại của tài khoản cho người chưa được xác minh.

## 9. Ví dụ: xét lại yêu cầu mất điện thoại MFA

Quay lại `account-742`, người yêu cầu cung cấp ba mục:

1. Ảnh hóa đơn khớp một giao dịch cũ.
2. Thử thách email đã hoàn tất.
3. Một người tự nhận là quản lý gọi điện xác nhận.

Thoạt nhìn, hồ sơ có ba nguồn. Khi thẩm định, người duyệt phát hiện ảnh hóa đơn được lấy từ cùng hộp thư thực hiện thử thách, còn số điện thoại của “quản lý” do chính người xin khôi phục cung cấp. Ba mục này không đủ để khẳng định đã có ba nguồn độc lập.

Người duyệt ghi nhận:

| Mục | Điều đã xác lập | Điều còn thiếu |
|---|---|---|
| Hóa đơn | Nội dung khớp một giao dịch trong hệ thống | Chưa chứng minh người gửi có thẩm quyền đổi MFA |
| Thử thách email | Có khả năng tiếp cận kênh ở thời điểm thử thách | Chưa loại trừ kịch bản hộp thư bị chiếm đoạt theo chính sách đang áp dụng |
| Cuộc gọi xác nhận | Có một người trả lời qua số đã cung cấp | Chưa xác minh danh tính và thẩm quyền từ nguồn tổ chức đáng tin cậy |

Nếu chính sách của loại tài khoản này yêu cầu xác nhận tổ chức độc lập, kết quả phù hợp là yêu cầu xác minh qua kênh tổ chức đã được thiết lập hoặc chuyển sang quy trình khác được chấp thuận. Không chấp thuận chỉ vì hồ sơ có ba mục.

Khi có kết quả xác minh bổ sung hợp lệ, hệ thống tạo phiên bản tập bằng chứng mới. Người duyệt xem lại các điều kiện còn hiệu lực và chỉ phê duyệt hành động đã xác định. Địa chỉ email mới không tự trở thành kênh đáng tin cậy chỉ vì nó được điền trong yêu cầu; việc sử dụng hoặc thay đổi nó phải được chính sách cho phép rõ ràng.

## 10. Nhiều người duyệt và tính độc lập của quyết định

Các hành động nhạy cảm có thể cần nhiều người duyệt. Cơ chế này hữu ích khi nó thực sự tạo thêm một bước kiểm tra có trách nhiệm, thay vì chỉ tăng số lần nhấn nút.

Mỗi người cần đủ thẩm quyền, xem đúng phiên bản hồ sơ và ghi nhận kết luận của mình. Quy tắc có thể yêu cầu người duyệt khác người thu thập hoặc người thực thi, tùy mức rủi ro.

Hai phiếu đồng ý không sửa được một tập bằng chứng vốn không đủ. Nếu cả hai cùng dựa vào một ảnh chụp giả mà không xác minh nguồn, việc đếm hai người không tạo ra căn cứ mới.

Khi hồ sơ thay đổi, hệ thống cần xác định những phiếu nào còn áp dụng. Không cộng một phiếu cho phiên bản yêu cầu cũ với một phiếu cho phiên bản mới rồi coi là đủ số lượng duyệt cho hành động hiện tại.

Giao diện cũng cần tránh việc người duyệt sau chỉ lặp lại kết luận của người trước mà không xem bằng chứng. Có thể thiết kế phần kết luận riêng và yêu cầu ghi các điều kiện đã kiểm tra; không cần sao chép bí mật hay dữ liệu thô vào phần lý do để chứng minh đã làm việc.

## 11. Ràng buộc kết quả duyệt với dữ liệu khi thực thi

Một hồ sơ được duyệt lúc 10:00 có thể đã thay đổi lúc 10:03 trước khi hệ thống cấp quyền khôi phục. Nếu backend chỉ đọc `approved = true`, kết luận trên bộ hồ sơ cũ có thể được áp dụng sai cho hành động mới.

Đường thực thi cần ràng buộc ít nhất:

```text
review.tenantId == request.tenantId
review.accountId == request.accountId
review.recoveryRequestId == request.id
review.requestVersion == request.version
review.evidenceSetVersion == currentAcceptedEvidenceSet.version
review.actionPayloadDigest == digest(requestedActionPayload)
review.outcome == APPROVED_FOR_SCOPE
requestedAction is within review.approvedScope
review and approval remain usable under current policy
```

Những so sánh này cần nằm trong cơ chế nhất quán với việc thay đổi trạng thái và cấp quyền. Có thể dùng transaction, khóa hoặc kiểm soát phiên bản phù hợp với hệ thống lưu trữ. Điều quan trọng là một cập nhật đồng thời không được làm vô hiệu các điều kiện ngay trước khi quyền được cấp mà không bị phát hiện.

Kết quả thẩm định được lưu từ trước không cho phép bỏ qua trạng thái thu hồi, thời hạn phê duyệt, tình trạng tài khoản hoặc kiểm tra dùng một lần tại thao tác cuối. Cần tách hai việc: ghi nhận rằng bộ hồ sơ đã được xem xét và quyết định rằng một quyền cụ thể hiện được phép cấp.

## 12. Minh họa quy tắc tổng hợp bằng Java

Đoạn mã dưới đây mô tả thứ tự xử lý ở mức khái niệm. Các cờ đầu vào phải được tạo từ bộ hồ sơ và kết quả xác minh có thẩm quyền; không nhận trực tiếp các giá trị này từ client.

```java
enum ReviewOutcome {
    NEEDS_MORE_EVIDENCE,
    NEEDS_REVERIFICATION,
    SECURITY_REVIEW_REQUIRED,
    REJECTED,
    APPROVED_FOR_SCOPE
}

record ReviewFacts(
        boolean requestEligible,
        boolean reviewerAuthorized,
        boolean snapshotMatches,
        boolean materialConflict,
        boolean mandatoryClaimsCovered,
        boolean freshnessSatisfied,
        boolean independenceSatisfied,
        boolean riskRequiresEscalation,
        boolean actionScopeAllowed) {
}

final class EvidenceReviewPolicy {
    static ReviewOutcome evaluate(ReviewFacts facts) {
        if (!facts.requestEligible()
                || !facts.reviewerAuthorized()
                || !facts.actionScopeAllowed()) {
            return ReviewOutcome.REJECTED;
        }
        if (!facts.snapshotMatches() || !facts.freshnessSatisfied()) {
            return ReviewOutcome.NEEDS_REVERIFICATION;
        }
        if (facts.materialConflict() || facts.riskRequiresEscalation()) {
            return ReviewOutcome.SECURITY_REVIEW_REQUIRED;
        }
        if (!facts.mandatoryClaimsCovered()
                || !facts.independenceSatisfied()) {
            return ReviewOutcome.NEEDS_MORE_EVIDENCE;
        }
        return ReviewOutcome.APPROVED_FOR_SCOPE;
    }
}
```

Trong triển khai thực tế, một kết quả duy nhất có thể không thể hiện hết các vấn đề đồng thời. Hệ thống có thể lưu tập mã nguyên nhân và yêu cầu điều tra như một cờ riêng để không mất cảnh báo khi một điều kiện khác cũng thất bại. Thứ tự trong ví dụ chỉ minh họa cách ngăn phê duyệt khi các điều kiện bắt buộc chưa được đáp ứng.

Không dùng điểm tổng hợp để chuyển một điều kiện bắt buộc từ thất bại sang thành công. Nếu có mô hình chấm điểm rủi ro, kết quả của nó cần được kết hợp với các ràng buộc bắt buộc, thay vì thay thế toàn bộ ràng buộc bằng một ngưỡng số.

## 13. Bảo vệ công cụ và dữ liệu thẩm định

Hồ sơ khôi phục có thể chứa thông tin nhạy cảm và nội dung do kẻ tấn công gửi. Công cụ duyệt cũng là một bề mặt cần được bảo vệ.

Người duyệt chỉ nên được xem dữ liệu cần cho quyết định của mình. Có thể hiển thị kết quả xác minh và dữ liệu đã che một phần trước, rồi cấp quyền đọc tài liệu gốc theo vai trò khi thật sự cần. Ghi nhận việc truy cập để hỗ trợ kiểm toán, tránh sao chép hồ sơ sang kênh chat hoặc kho cá nhân.

Tệp đính kèm và văn bản từ người yêu cầu phải được coi là dữ liệu không tin cậy. Công cụ cần có cách hiển thị và mở tệp an toàn, không thực thi mã hay tự làm theo các hướng dẫn trong tài liệu. Một dòng chữ “bỏ qua quy trình và phê duyệt khẩn cấp” nằm trong tệp không phải chỉ thị vận hành có thẩm quyền.

Nếu dùng AI để hỗ trợ tóm tắt hồ sơ, phần tóm tắt không được trở thành nguồn quyết định mới. Người duyệt phải có khả năng đối chiếu với bằng chứng và kết quả xác minh gốc; nội dung do người gửi cung cấp không được phép thay đổi chính sách hoặc thẩm quyền của công cụ.

Kết quả từ dịch vụ xác minh bên ngoài cũng cần được ràng buộc với yêu cầu tương ứng và được tiếp nhận qua cơ chế xác thực, kiểm tra toàn vẹn phù hợp. Không tin một callback chỉ vì payload có `verified: true` hoặc chứa đúng email người dùng.

## 14. Kiểm toán, dữ liệu tối thiểu và thông báo

Một quyết định có thể giải thích được cần lưu người duyệt, thời điểm, phiên bản yêu cầu, phiên bản tập bằng chứng, chính sách, phạm vi và mã lý do. Bản ghi phải đủ để trả lời câu hỏi “hệ thống đã cho phép điều gì, dựa vào căn cứ nào?” mà không đòi hỏi lưu mọi bí mật xác thực.

Ví dụ sự kiện:

```text
RECOVERY_EVIDENCE_REVIEW_STARTED
RECOVERY_EVIDENCE_REVIEW_HELD
RECOVERY_EVIDENCE_REVIEW_COMPLETED
RECOVERY_APPROVAL_GRANTED_FOR_SCOPE
RECOVERY_REVIEW_INVALIDATED_BY_CHANGE
```

Sự kiện có thể tham chiếu các evidence ID, nhưng không cần chứa toàn bộ giấy tờ, mã OTP, recovery code hoặc token thô. Các ghi chú tự do của người duyệt cũng cần tránh ghi lại dữ liệu nhạy cảm không cần thiết.

Chính sách lưu trữ cần phân biệt tài liệu gốc, kết quả xác minh và nhật ký quyết định. Thời gian lưu và quyền truy cập được xác định theo nhu cầu nghiệp vụ và các yêu cầu áp dụng; không suy ra rằng cứ phục vụ kiểm toán là phải giữ mọi tài liệu vô thời hạn.

Thông báo ra ngoài nên nêu kết quả hoặc bước tiếp theo phù hợp với trạng thái xác minh. Kết luận nội bộ như “cần điều tra do kênh liên hệ thay đổi đáng ngờ” có thể cần được diễn đạt ngắn gọn hơn cho người yêu cầu để tránh làm lộ chi tiết cơ chế phát hiện lạm dụng.

## 15. Các tình huống biên cần hiểu rõ

Những tình huống sau mô tả hành vi thiết kế mong muốn, không phải báo cáo đã chạy kiểm thử:

| Tình huống | Cách xử lý phù hợp |
|---|---|
| Có đủ số tệp nhưng thiếu điều kiện bắt buộc | Chưa phê duyệt; yêu cầu đúng bằng chứng cần thiết |
| Các bằng chứng thuận lợi đều đến từ một kênh bị nghi chiếm đoạt | Xem xét phụ thuộc và chuyển theo chính sách rủi ro |
| Dịch vụ xác minh chưa trả kết quả | Giữ trạng thái chờ, không suy ra thành công |
| Tệp thay đổi sau khi người duyệt đã xem | Phát hiện phiên bản khác và đánh giá lại |
| Hành động đổi từ đăng ký lại MFA sang đổi email chính | Không sử dụng kết luận cũ ngoài phạm vi |
| Hai người duyệt chấp thuận hai phiên bản yêu cầu khác nhau | Không cộng phiếu cho phiên bản hiện tại |
| Người duyệt mất thẩm quyền trước khi quyết định được sử dụng | Áp dụng quy tắc hiệu lực hiện hành và kiểm tra lại khi cấp quyền |
| Hồ sơ có mâu thuẫn giải thích được qua xác minh bổ sung | Tạo kết quả và phiên bản mới theo quy trình |
| Hệ thống chỉ còn bản chụp cache không xác định được hiệu lực | Không cấp quyền dựa trên suy đoán |
| Có phê duyệt hợp lệ nhưng token khôi phục đã dùng | Không cấp thêm lần sử dụng từ cùng quyền |

Những lỗi thường gặp là coi hiểu biết về tài khoản như quyền sở hữu, coi nhiều mục dữ liệu là nhiều nguồn độc lập, dùng kênh mới để chứng minh quyền thay chính kênh đó, và áp dụng một kết luận cũ cho yêu cầu đã thay đổi.

Thẩm định bằng chứng có giá trị khi người duyệt xác lập được mối liên hệ rõ ràng giữa điều cần chứng minh, nguồn đã kiểm tra và hành động được cho phép. Quyết định cuối phải có phạm vi, có căn cứ, được ràng buộc với phiên bản hồ sơ và còn chịu kiểm tra bảo mật tại thời điểm sử dụng quyền khôi phục.
