# Hạn chế khi dùng điện thoại làm phương án khôi phục dự phòng (Telephony fallback restrictions)

Khi người dùng không nhận được SMS hoặc không còn dùng được phương thức xác thực chính, hệ thống có thể đề xuất một phương án dự phòng qua điện thoại. Thao tác này ảnh hưởng trực tiếp đến ranh giới bảo vệ tài khoản: một lỗi chuyển tin không được tự biến thành quyền dùng phương thức yếu hơn hoặc bỏ qua bằng chứng còn thiếu.

Trong chương **SMS Voice Recovery** của module `SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY`, bài học này trình bày cách giới hạn fallback qua SMS và cuộc gọi thoại. Mục tiêu là hỗ trợ người mất mật khẩu, MFA, passkey hoặc thiết bị xác thực bằng một luồng có kiểm soát, đồng thời giảm nguy cơ chiếm đoạt tài khoản, lạm dụng gửi mã và né giới hạn session.

## 1. Phân biệt ba loại chuyển phương án

Thuật ngữ *telephony fallback* thường bị dùng chung cho các thay đổi có mức ảnh hưởng khác nhau:

| Loại thay đổi | Ví dụ | Quyết định cần có |
| --- | --- | --- |
| Chuyển tuyến chuyển tin | Đổi nhà cung cấp SMS vì một tuyến gặp lỗi | Tuyến mới có được phép xử lý cùng dữ liệu và giữ đúng hợp đồng challenge không? |
| Chuyển kênh trong mạng điện thoại | Từ SMS sang cuộc gọi đến số đã liên kết | Cuộc gọi có được phép trong ngữ cảnh này, với cùng ràng buộc xác minh không? |
| Chuyển phương thức chứng minh | Không dùng được passkey nên yêu cầu khôi phục bằng SMS | Bằng chứng qua điện thoại có đủ cho mục đích này hay cần quy trình mạnh hơn? |

Đổi tuyến hoặc đổi kênh là thay đổi cách chuyển một bằng chứng. Chuyển từ passkey sang SMS có thể thay đổi cả thuộc tính an ninh của bằng chứng. Ba trường hợp này không nên được xử lý bằng một cờ chung như `fallback=true`.

Cũng cần tách **không nhận được tin** với **không còn kiểm soát số điện thoại**. Một cuộc gọi có thể giúp khi SMS bị chậm nhưng người dùng vẫn nhận cuộc gọi ở số đã đăng ký. Cuộc gọi đến chính số đó không giải quyết việc số đã bị chiếm SIM, chuyển quyền nhận hoặc cấp lại cho người khác.

## 2. Ngăn fallback trở thành đường hạ mức xác minh

Kẻ tấn công có thể chủ động báo mất thiết bị, bỏ qua bước passkey, gửi nhiều yêu cầu thất bại hoặc khai rằng không nhận được SMS. Những hành vi đó chưa chứng minh danh tính và không tự tạo quyền sử dụng phương thức dự phòng.

Một thiết kế nguy hiểm là:

```text
Nếu phương thức chính thất bại ba lần:
    cho phép SMS khôi phục mọi loại tài khoản;
    nếu SMS tiếp tục thất bại thì gọi đến số người yêu cầu nhập.
```

Với thiết kế này, kẻ tấn công chỉ cần tạo đủ lỗi để đi tới đường yếu hơn. Số lần thất bại trở thành điều kiện mở khóa quyền thay vì tín hiệu cần kiểm soát.

Thiết kế cần giữ các ràng buộc sau:

- Mục đích khôi phục vẫn giữ nguyên khi chuyển phương án.
- Yêu cầu về bằng chứng do chính sách tài khoản quyết định, không do số lần chuyển tin thất bại quyết định.
- Phương thức dự phòng phải được phê duyệt cho đúng loại tài khoản và thao tác.
- Những bằng chứng còn thiếu không được tự đánh dấu hoàn thành khi bật fallback.
- Endpoint web, ứng dụng di động, API cũ và công cụ hỗ trợ phải thực thi cùng giới hạn nghiệp vụ.

OWASP mô tả fallback yếu và endpoint cũ thiếu kiểm soát là nguồn gây hạ mức MFA. Hướng dẫn của OWASP yêu cầu kiểm soát việc chuyển từ phương thức chống phishing sang phương thức có mức bảo đảm thấp hơn bằng chính sách được ghi nhận rõ. [OWASP: MFA Downgrade Attacks](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html#mfa-downgrade-attacks).

SMS và cuộc gọi đến cùng số chia sẻ nhiều rủi ro. Hoàn thành cả hai không tự tạo thành hai yếu tố độc lập. Tương tự, việc đổi nhà cung cấp gửi không làm một OTP nhập tay trở thành bằng chứng chống phishing như passkey.

NIST coi xác thực ngoài băng qua mạng điện thoại công cộng là phương thức bị hạn chế. Trong phạm vi áp dụng của tiêu chuẩn, việc chấp nhận phương thức này cần đánh giá rủi ro, cung cấp lựa chọn không bị hạn chế phù hợp và có kế hoạch chuyển đổi. Không nên diễn giải một cơ chế fallback qua điện thoại là tự đáp ứng toàn bộ yêu cầu khôi phục của NIST. [NIST SP 800-63B, Restricted Authenticators](https://pages.nist.gov/800-63-4/sp800-63b.html#restricted-authenticators).

## 3. Xác định rõ trường hợp được phép và bị từ chối

Bảng sau là chính sách minh họa cho một sản phẩm; không phải danh sách cấm chung cho mọi hệ thống:

| Ngữ cảnh | Có thể cho fallback qua điện thoại? | Điều kiện hoặc hướng xử lý |
| --- | --- | --- |
| SMS chậm, số đã đăng ký còn hiệu lực, thao tác thông thường | Có thể | Người dùng chủ động yêu cầu, đủ thời gian chờ, còn ngân sách, rủi ro cho phép |
| Đổi nhà cung cấp cho cùng số và cùng mục đích | Có thể | Tuyến được phê duyệt, giữ giới hạn và trạng thái challenge |
| Người dùng mất quyền nhận ở số đã đăng ký | Không giải quyết bằng cách gọi cùng số | Chuyển sang bằng chứng độc lập hoặc quy trình khôi phục khác |
| Yêu cầu gọi đến số mới do người đang bị khóa ngoài khai báo | Không | Cần quy trình liên kết số hoặc xác minh độc lập trước |
| Có tín hiệu chiếm SIM, chuyển số đáng ngờ hoặc số bị báo mất | Không tự chuyển SMS sang thoại | Đánh giá rủi ro của cả nhóm phương thức dựa trên số đó |
| Khôi phục tài khoản quản trị, gỡ MFA hoặc thay yếu tố bảo vệ quan trọng | Không tự cho phép chỉ vì kênh chính lỗi | Cần chính sách và bằng chứng mạnh hơn cho đúng thao tác |
| Đã hết lượt nhập mã hoặc ngân sách gửi | Không dùng đổi kênh để mở thêm lượt | Giữ bộ đếm, thời gian chờ và hướng khôi phục phù hợp |
| Hệ thống kiểm tra rủi ro không trả kết quả | Phụ thuộc chính sách dữ liệu chưa xác định | Không mặc định cho phép vì thiếu dữ liệu |

Không nên áp dụng một chuỗi cố định như “SMS lỗi thì luôn gọi” cho mọi tài khoản. Tài khoản thông thường, tài khoản có dữ liệu nhạy cảm và tài khoản có quyền quản trị có thể có yêu cầu khôi phục khác nhau.

Cũng không nên tự động tạo nhiều tin hoặc cuộc gọi chỉ để người dùng đủ điều kiện thấy nút fallback. Khoảng chờ và điều kiện chuyển kênh phải có mục đích rõ ràng; số lần thử không phải bằng chứng an ninh.

## 4. Ràng buộc số nhận và loại đường dây

Máy chủ phải chọn đích từ các liên kết khôi phục đã được phê duyệt, thay vì tin trường `phoneNumber` trong yêu cầu fallback. Một liên kết cần có định danh nội bộ, trạng thái, thời điểm xác minh và phiên bản để phát hiện thay đổi.

Các kiểm tra quan trọng gồm:

1. Số nhận còn thuộc liên kết khôi phục được phép của tài khoản.
2. Liên kết không bị gỡ, đình chỉ hoặc thay thế trong lúc luồng đang chạy.
3. Challenge tham chiếu đúng phiên bản liên kết.
4. Kênh thoại hoặc SMS được phép cho loại đường dây và tuyến đang dùng.
5. Quốc gia đích, nhóm số và tuyến cước nằm trong phạm vi vận hành được phê duyệt.

Số mới được xác minh chỉ chứng minh người yêu cầu tiếp cận số mới. Nó không tự chứng minh quyền gắn số mới vào tài khoản cũ. Việc đổi số cần quyền từ một phiên đủ mạnh hoặc một quy trình khôi phục riêng đã được phê duyệt.

Số VoIP, số bàn, tổng đài chung, số có máy nhánh hoặc số nhận tạm thời có đặc điểm khác nhau. Sản phẩm có thể hạn chế một số loại đường dây theo mô hình rủi ro, nhưng không nên tuyên bố mọi số VoIP đều gian lận hoặc mọi số di động đều an toàn. Dữ liệu phân loại đường dây cũng có thể thiếu hoặc thay đổi.

Mã quốc gia của số đích dùng để kiểm soát tuyến gửi; vị trí IP của trình duyệt là một tín hiệu khác. Không thể thay việc kiểm tra đích cuộc gọi bằng kiểm tra người gọi đang truy cập từ quốc gia nào.

## 5. Giới hạn riêng của cuộc gọi thoại

Cuộc gọi dự phòng có những điểm cần kiểm soát ngoài các ràng buộc chung của OTP:

| Tình huống | Hạn chế cần có |
| --- | --- |
| Cuộc gọi vào hộp thư thoại | Tránh để mã được đọc và lưu lại tự động khi chưa có tương tác của người nhận |
| Số có chuyển tiếp cuộc gọi | Không giả định người bắt máy đang giữ thiết bị đã đăng ký |
| Tổng đài hoặc điện thoại dùng chung | Không giả định người nghe là chủ tài khoản chỉ vì cuộc gọi đã kết nối |
| Bên nhận giữ cuộc gọi quá lâu hoặc yêu cầu lặp liên tục | Giới hạn thời lượng, số lần đọc lại và số cuộc gọi theo chính sách |
| Người gọi đến bộ phận hỗ trợ hiển thị số quen thuộc | Không dùng Caller ID làm bằng chứng sở hữu tài khoản |
| Nhà cung cấp báo `ANSWERED` hoặc `COMPLETED` | Chỉ ghi nhận trạng thái chuyển tin, không đánh dấu xác minh thành công |

Có thể yêu cầu người nhận bấm một phím được chọn trước khi hệ thống đọc mã, nhằm giảm nguy cơ để mã trong hộp thư thoại tự động. Tài liệu Twilio Verify mô tả cơ chế yêu cầu bấm một chữ số ngẫu nhiên trước khi đọc token. Tuy nhiên, tương tác bàn phím chỉ cho thấy có bên phản hồi cuộc gọi; đó chưa phải xác minh danh tính chủ tài khoản. [Twilio: Voice verification channel](https://www.twilio.com/docs/verify/authentication-channels#voice).

Trong luồng minh họa của bài, người nhận vẫn phải nhập OTP vào đúng ngữ cảnh khôi phục trên ứng dụng. Việc bấm phím để nghe mã không được thay cho bước nhập mã này. Nếu sản phẩm xây dựng một giao thức xác minh hoàn toàn trong cuộc gọi, giao thức đó cần được thiết kế và đánh giá riêng, không kế thừa quyền chỉ từ callback cuộc gọi đã hoàn tất.

Không ghi âm cuộc gọi chứa mã theo mặc định. Nếu dịch vụ có lưu âm thanh, bản ghi hoặc bản chuyển lời thành văn bản, cần đánh giá nguy cơ lộ bí mật, quyền truy cập và thời gian lưu; tránh để OTP đi vào công cụ phân tích hội thoại hoặc log hỗ trợ.

Khả năng tiếp cận cũng cần được tính đến. Người khiếm thính, người không thể nhận cuộc gọi hoặc người đang dùng thiết bị không hỗ trợ tương tác bàn phím cần có lựa chọn phù hợp. Phương án thay thế vẫn phải đáp ứng yêu cầu bằng chứng của thao tác, thay vì bỏ bước xác minh để giảm khó khăn sử dụng.

## 6. Đánh giá rủi ro trước và sau khi chuyển kênh

Một quyết định fallback có thời điểm hiệu lực. Nó không nên là giấy phép dùng mãi dù số điện thoại, chính sách hoặc tình trạng tài khoản đã thay đổi.

Đánh giá ít nhất các nhóm thông tin sau:

- Mức nhạy cảm của tài khoản và mục đích: đặt lại mật khẩu, thay MFA, đăng ký passkey mới hoặc khôi phục quyền quản trị.
- Tuổi và trạng thái của liên kết số, thay đổi số trong tài khoản, sự kiện mất số hoặc nghi bị chiếm quyền nhận.
- Tín hiệu nhà mạng nếu có: thay SIM, chuyển số, chuyển tiếp hoặc phân loại đường dây phù hợp phạm vi dữ liệu được cung cấp.
- Nguồn yêu cầu, hành vi mở nhiều luồng, đổi kênh liên tục và lịch sử thất bại bất thường.
- Tình trạng tuyến gửi, ngân sách còn lại và khả năng thực thi giới hạn của hệ thống.

Mỗi tín hiệu cần có nguồn, thời điểm quan sát và trạng thái chất lượng dữ liệu. Không có kết quả kiểm tra chiếm SIM không có nghĩa là đã kiểm tra và không thấy chiếm SIM.

Có thể biểu diễn kết quả rủi ro bằng ba trạng thái:

| Trạng thái | Ý nghĩa đối với fallback |
| --- | --- |
| Đủ điều kiện theo chính sách | Có thể tiếp tục qua các cổng giới hạn còn lại |
| Có dấu hiệu không chấp nhận được | Từ chối phương án điện thoại hoặc yêu cầu bằng chứng độc lập |
| Chưa xác định | Áp dụng quy tắc cho dữ liệu thiếu; không tự chuyển thành “an toàn” |

Đối với thao tác nhạy cảm cần tín hiệu cụ thể, khi dịch vụ rủi ro gặp lỗi, có thể tạm ngừng fallback điện thoại và mở hướng xác minh khác đã được thiết kế trước. Không cần khóa mọi hoạt động của tài khoản hoặc chặn các phương thức mạnh vẫn dùng được.

Nếu số bị gỡ sau khi người dùng yêu cầu cuộc gọi nhưng trước khi công việc được gửi, bộ xử lý phải phát hiện liên kết không còn hợp lệ. Nếu rủi ro tăng sau khi đã nghe mã nhưng trước lúc cấp quyền khôi phục, chính sách cần được đánh giá lại ở điểm cấp quyền. Mã đúng không xóa một tín hiệu rủi ro mới xuất hiện.

## 7. Giữ chung hạn mức và thời hạn qua các kênh

Chuyển từ SMS sang thoại không được tạo một bộ đếm độc lập cho phép người yêu cầu vượt tổng ngân sách. Cần phân biệt:

| Loại giới hạn | Phạm vi áp dụng |
| --- | --- |
| Số lần chuyển mã | Cộng dồn SMS và cuộc gọi trong cùng luồng hoặc challenge logic |
| Số cuộc gọi | Giới hạn bổ sung riêng cho kênh thoại |
| Số lần chuyển kênh | Ngăn vòng lặp SMS → thoại → SMS để né chính sách |
| Số lần nhập sai | Giữ xuyên suốt bước chứng minh, có giới hạn tổng hợp theo tài khoản |
| Thời hạn challenge và luồng | Không bắt đầu lại chỉ vì đổi tuyến hoặc đổi kênh |
| Ngân sách tài khoản, số nhận và chi phí | Cộng dồn qua nhiều luồng và nhà cung cấp |

Một cấu hình minh họa có thể cho tối đa ba lần chuyển mã, trong đó không quá một cuộc gọi, và chỉ cho một lần chuyển SMS sang thoại. Challenge sống năm phút từ lúc cấp đầu; tổng cộng tối đa năm lần nhập sai cho bước đang thực hiện; yêu cầu cuộc gọi chỉ được xem xét sau ít nhất 60 giây và vẫn phải qua chính sách rủi ro. Các giá trị này là giả định học tập, không phải ngưỡng bắt buộc của tiêu chuẩn.

Với cấu hình đó, sau hai lần SMS, người dùng chỉ còn tối đa một lần chuyển mã. Bật thoại không tạo thêm ba lần gửi. Nếu đã dùng hết năm lượt nhập sai, đổi kênh không khôi phục lượt đoán. Mở luồng mới cũng phải qua các giới hạn tổng hợp theo tài khoản và số nhận.

Có hai cách quản lý mã khi chuyển kênh, nhưng cần chọn rõ:

| Cách | Ràng buộc phải giữ |
| --- | --- |
| Giữ cùng mã trong một challenge logic | Cùng thời hạn, cùng lượt thử còn lại; thành công một lần làm mọi bản sao mất hiệu lực |
| Cấp phiên bản mã mới | Vô hiệu phiên bản cũ nguyên tử; giữ các bộ đếm tổng hợp và mốc kết thúc cứng của luồng |

Không được để việc đổi nhà cung cấp vô tình tạo nhiều bộ mã cùng được chấp nhận. Nếu nhà cung cấp quản lý mã, ứng dụng phải biết chính xác định danh xác minh nào còn hiệu lực và từ chối kết quả không thuộc phiên bản được chấp nhận. Nếu không thể thực thi hợp đồng này, không nên mở tuyến fallback đó.

Yêu cầu lặp do mất phản hồi mạng phải dùng cùng khóa idempotency. Cùng một thao tác logic chỉ giữ chỗ ngân sách và tạo công việc gọi một lần. Một thao tác chủ động mới vẫn phải vượt qua khoảng chờ và mọi giới hạn hiện hành.

## 8. Thực thi quyết định tại máy chủ

Ẩn nút “Gọi cho tôi” chưa đủ để bảo vệ endpoint. Client có thể gọi API trực tiếp, nên máy chủ phải tự xác định những kênh được phép ở từng ngữ cảnh.

Một yêu cầu minh họa chỉ nêu kênh mong muốn, không cho đổi đích nhận:

```http
POST /account-recovery/flows/{flowId}/telephony-fallback
Content-Type: application/json
Idempotency-Key: <khoa-cua-mot-thao-tac-nguoi-dung>

{
  "challengeId": "<tham-chieu-challenge>",
  "targetChannel": "VOICE"
}
```

`VOICE` ở đây là giá trị trong hợp đồng ứng dụng minh họa, không phải tên tham số của một nhà cung cấp cụ thể. Máy chủ chọn số, tuyến và các tùy chọn gửi từ dữ liệu đã được phê duyệt.

Quá trình chấp nhận yêu cầu cần thực hiện theo thứ tự có kiểm soát:

1. Kiểm tra hình dạng yêu cầu và ràng buộc với đúng ngữ cảnh luồng; bảo vệ yêu cầu dùng cookie khỏi giả mạo phù hợp.
2. Nạp tài khoản, challenge, mục đích, liên kết số và trạng thái hiện hành.
3. Đối chiếu khóa idempotency với fingerprint gồm luồng, challenge, đích nội bộ, phiên bản liên kết và kênh.
4. Xác định chính sách có cho phép phương án này và còn bằng chứng nào cần có.
5. Kiểm tra rủi ro, khoảng chờ, thời hạn và các giới hạn tổng hợp.
6. Giữ chỗ ngân sách, ghi chuyển trạng thái và công việc gửi bằng thao tác phối hợp nguyên tử.
7. Sau khi ghi dữ liệu thành công, bộ xử lý mới gọi nhà cung cấp ngoài giao dịch nghiệp vụ.

Việc kiểm tra và ghi nhận phải được bảo vệ khỏi yêu cầu đồng thời trên nhiều instance. Không dùng cách “đọc còn một lượt, gọi nhà cung cấp, rồi mới trừ lượt”: hai yêu cầu có thể cùng thấy một lượt còn lại và đều tạo cuộc gọi.

Có thể dùng giao dịch cơ sở dữ liệu hoặc cơ chế điều phối tương đương cho challenge, hạn mức và công việc gửi. Kết quả của một hàm kiểm tra chính sách dựa trên ảnh chụp dữ liệu chưa đủ để bảo đảm quyền gửi; cần kiểm tra lại các điều kiện có thể thay đổi tại thao tác giữ chỗ.

## 9. Lỗi nhà cung cấp không được làm mất các ràng buộc

Mạng điện thoại và dịch vụ chuyển mã có thể trả trạng thái chậm, trùng hoặc không xác định. Cần xử lý lỗi theo trạng thái nghiệp vụ thay vì suy luận rằng mỗi lỗi là một quyền gửi tiếp.

| Sự kiện | Cách xử lý phù hợp |
| --- | --- |
| SMS chưa có báo cáo giao tin | Có thể xét fallback theo thời gian chờ và chính sách; không coi sự im lặng là bằng chứng SMS chắc chắn chưa tới |
| API gửi timeout | Giữ trạng thái chưa xác định và hạn mức đã giữ chỗ; đối soát hoặc thử lại cùng định danh khi hỗ trợ |
| Một cuộc gọi đã được ghi nhận nhưng bộ xử lý khởi động lại | Nhận diện công việc lặp, tránh tạo một thao tác gọi mới không kiểm soát |
| Callback cuộc gọi báo hoàn tất | Chỉ cập nhật trạng thái chuyển tin; không cấp quyền khôi phục |
| Callback SMS cũ đến sau khi chuyển kênh | Không tạo thêm lượt thử, không phục hồi phiên bản mã bị thu hồi |
| Challenge hết hạn khi công việc còn chờ | Bỏ qua lần chuyển chưa thực hiện; không tự gia hạn mã |
| Kho kiểm soát hạn mức không khả dụng | Tạm ngừng việc tạo lần gửi mới nếu không bảo đảm được giới hạn; giữ các hướng xác minh khác đủ điều kiện |

Fallback có thể được phép trong lúc chưa biết chắc SMS đã giao hay chưa, nếu chính sách đã tính đến tình huống hai bản chuyển cùng đến. Khi đó, ngân sách của lần SMS vẫn được giữ và hợp đồng mã phải xử lý được cả hai bản. Không cần giả vờ rằng tuyến đầu đã hủy chắc chắn mới cho người dùng đi tiếp.

Công việc gửi bền vững giúp tránh mất liên hệ giữa dữ liệu nghiệp vụ và yêu cầu chuyển mã, nhưng không tự bảo đảm nhà cung cấp chỉ thực hiện đúng một lần. Cần tận dụng idempotency hoặc đối soát khi có, giới hạn thử lại và chấp nhận khả năng chuyển trùng trong phạm vi đã kiểm soát nếu nhà cung cấp không hỗ trợ bảo đảm mạnh hơn.

Trước khi gọi, bộ xử lý kiểm tra challenge còn hiệu lực, phiên bản số còn đúng, kênh chưa bị tắt và công việc chưa bị hủy. Nếu cuộc gọi đã được nhà cung cấp khởi tạo, không nên hứa có thể ngăn mọi lần đọc mã sau khi người dùng xác minh ở kênh khác. Hàng rào quyết định vẫn là endpoint xác minh: mã đã dùng hoặc hết hạn phải bị từ chối.

Giới hạn chi phí cần được thực thi ở cả ứng dụng và cấu hình nhà cung cấp: chỉ bật kênh đang sử dụng, chỉ mở vùng đích cần thiết, giới hạn số cuộc gọi, thời lượng và tần suất theo chính sách. Twilio nêu toll fraud là tình huống bị lợi dụng để tạo nhiều cuộc gọi tới số có cước cao, đồng thời khuyến nghị tắt kênh không dùng và kiểm soát đích gửi. [Twilio: Preventing Fraud in Verify](https://www.twilio.com/docs/verify/preventing-toll-fraud).

Kiểm tra nguồn callback theo cơ chế của nhà cung cấp, đối chiếu định danh lần gửi và xử lý lặp an toàn. Dữ liệu từ client như `smsFailed=true` hay `callCompleted=true` chỉ là đầu vào chưa tin cậy, không được dùng để bỏ chính sách hoặc xác minh thành công.

## 10. Giới hạn quyền sau khi xác minh qua fallback

Cho phép thực hiện cuộc gọi chỉ là quyền chuyển một challenge. Nhận cuộc gọi, nghe mã và nhập đúng mã cũng chưa tự hoàn tất mọi điều kiện khôi phục.

Một mô hình cần tách các kết quả sau:

```text
FALLBACK_DELIVERY_ALLOWED  -> Được chuyển mã qua kênh đã phê duyệt
TELEPHONY_EVIDENCE_PASSED  -> Đã hoàn thành bằng chứng qua điện thoại
RECOVERY_POLICY_SATISFIED -> Đã đủ các điều kiện cho mục đích khôi phục
RECOVERY_ACTION_COMPLETED -> Đã thực hiện đúng thao tác được cho phép
```

Không được nhảy trực tiếp từ trạng thái cuộc gọi đã kết nối sang khôi phục tài khoản. Cũng không tự gộp bằng chứng SMS và thoại cùng số để đánh dấu đủ hai yếu tố.

Khi đủ điều kiện, quyền tiếp tục cần có thời hạn ngắn, gắn với tài khoản, luồng và một mục đích cụ thể. Quyền đặt lại mật khẩu không đồng thời cho phép gỡ MFA, đổi email hoặc thêm passkey. Khôi phục khi mất khóa xác thực có thể dẫn tới đăng ký khóa mới theo quy trình riêng, không phải tái tạo khóa riêng từ mã điện thoại.

Tại thời điểm hoàn tất, kiểm tra lại liên kết số và các điều kiện rủi ro cần thiết. Nếu có thời gian chờ bắt buộc trước thay đổi nhạy cảm, việc chuyển sang thoại hoặc đổi tuyến không được bỏ khoảng chờ đó. Hết thời gian chờ cũng không thay thế một bằng chứng độc lập còn thiếu.

Việc xử lý session và refresh token phải gắn với sự kiện hoàn tất hoặc bằng chứng nguy cơ cụ thể. Không tự thu hồi mọi phiên chỉ vì ai đó xin gọi dự phòng nhiều lần; hành vi đó có thể bị người ngoài cố tình tạo ra. Sau khôi phục, thực hiện chính sách đăng nhập và các yếu tố còn hiệu lực phù hợp với thay đổi đã được phê duyệt.

Thông báo an ninh nên đi qua các kênh đã đăng ký thích hợp. Nếu số điện thoại đang bị nghi chiếm, chỉ thông báo về chính số đó sẽ không giúp chủ tài khoản phát hiện sự cố qua một kênh độc lập.

## 11. Ngoại lệ vận hành và trải nghiệm người dùng

Khi có sự cố diện rộng của tuyến SMS, biện pháp vận hành hợp lý là sử dụng tuyến hoặc phương thức dự phòng đã được phê duyệt, đồng thời giữ các điều kiện xác minh. Một cờ xử lý sự cố không được tự cho mọi tài khoản bỏ MFA hoặc gọi đến số mới.

Nếu cần ngoại lệ, nên ghi rõ phạm vi tài khoản, mục đích, thời hạn, bằng chứng thay thế, người chịu trách nhiệm và điều kiện thu hồi. Ngoại lệ không được xuất phát chỉ từ câu nói “khách hàng đang rất cần truy cập” hoặc việc nhân viên hỗ trợ thấy một Caller ID quen thuộc.

Bộ phận hỗ trợ phải dùng cùng chính sách với luồng tự phục vụ. Giao diện hỗ trợ có thể đề xuất tuyến khác hoặc đưa người dùng sang quy trình xác minh đã định nghĩa; không nên cung cấp một nút bỏ mọi hạn mức, đổi số và hoàn tất khôi phục trong cùng thao tác thiếu bằng chứng.

Đối với người dùng, giao diện cần giải thích được:

- Khi nào có thể yêu cầu cuộc gọi và cuộc gọi sẽ đến kênh đã đăng ký nào, trong phạm vi được phép hiển thị.
- Việc chuyển kênh có giữ mã hay làm mã trước mất hiệu lực.
- Thời hạn hiện tại của mã và số bước còn phải hoàn thành.
- Hướng xử lý khi không còn kiểm soát số hoặc không thể dùng cuộc gọi.

Không cần tiết lộ lý do rủi ro nội bộ như sự kiện thay SIM, danh sách chặn tuyến hoặc tình trạng tồn tại của tài khoản cho người chưa được xác minh. Có thể cung cấp thông báo chung và hướng tiếp tục phù hợp. Các mã HTTP, thời điểm chờ và danh sách phương thức trả ra cũng phải tránh tạo tín hiệu dò tài khoản.

Nếu không được phép dùng điện thoại dự phòng, hãy cung cấp phương án mạnh khác đã đăng ký, mã khôi phục đã lưu hoặc đường hỗ trợ được kiểm soát khi sản phẩm có hỗ trợ. Không được cam kết luôn phục hồi được tài khoản khi không còn bằng chứng đủ tin cậy, nhưng cũng không nên biến việc từ chối riêng kênh điện thoại thành khóa toàn bộ các phương thức đang hợp lệ.

## 12. Ví dụ diễn tiến và các thuộc tính cần kiểm chứng

Giả sử một tài khoản học tập có số khôi phục đã liên kết ổn định. Chính sách minh họa cho phép tối đa ba lần chuyển mã, không quá một cuộc gọi và một lần chuyển từ SMS sang thoại. Challenge được cấp lúc `09:00:00`, hết hạn lúc `09:05:00`, có tổng cộng năm lượt nhập sai. Trong ví dụ này, SMS và thoại chuyển cùng mã của một challenge logic.

| Thời điểm | Sự kiện | Kết quả mong đợi |
| --- | --- | --- |
| `09:00:00` | Ghi nhận lần SMS đầu | Đã dùng một lần chuyển mã; hạn dùng là `09:05:00` |
| `09:00:30` | Người dùng xin gọi trước khoảng chờ 60 giây | Chưa được gọi; không tạo công việc thoại |
| `09:01:00` | Người dùng chủ động xin gọi, còn đủ ngân sách và điều kiện | Ghi nhận một cuộc gọi; tổng số lần chuyển mã là hai |
| `09:01:01` | Client lặp lại cùng thao tác do mất phản hồi | Trả kết quả đã ghi nhận; không thêm cuộc gọi |
| `09:01:20` | Cuộc gọi được bắt máy, người nhận bấm phím để nghe mã | Chưa có bằng chứng OTP được xác minh |
| `09:01:40` | Người dùng nhập sai một lần | Còn bốn lượt nhập sai; đổi kênh không đặt lại bộ đếm |
| `09:02:00` | Người dùng nhập đúng mã trong luồng | Tiêu thụ challenge một lần và đánh giá các điều kiện khôi phục còn lại |
| `09:02:10` | Tin SMS đến muộn | Bản sao chứa mã đã dùng; không có thêm quyền xác minh |

Nếu cùng yêu cầu đó thuộc tài khoản quản trị đang khôi phục MFA và có tín hiệu chiếm SIM, bảng thời gian trên không tự làm cuộc gọi trở nên được phép. Chính sách phải chuyển người yêu cầu sang bằng chứng phù hợp với tình huống rủi ro. Tương tự, nếu người dùng không còn nhận được ở số đã liên kết, thay đích gọi bằng một số mới không phải cách hoàn thành luồng này.

Những tình huống sau cần được kiểm chứng khi triển khai:

| Tình huống | Thuộc tính cần giữ |
| --- | --- |
| Bỏ qua giao diện và gọi thẳng endpoint thoại | Máy chủ vẫn kiểm tra toàn bộ điều kiện fallback |
| Tạo đủ lỗi passkey hoặc báo mất thiết bị | Không tự mở quyền khôi phục bằng điện thoại |
| Hai instance đồng thời nhận yêu cầu chuyển kênh | Chỉ giữ chỗ số lần gửi và số lần chuyển kênh cho phép |
| Khóa idempotency được dùng lại với đích nội bộ hoặc kênh khác | Bị từ chối do fingerprint không khớp |
| Đã hết lượt nhập mã ở SMS rồi chọn thoại | Không được cấp thêm lượt đoán |
| Chuyển giữa nhiều nhà cung cấp | Không tạo các bộ mã độc lập cùng mở quyền khôi phục |
| Số nhận bị đổi hoặc gỡ trong khi công việc đang chờ | Không chuyển mã hoặc cấp quyền dựa trên liên kết cũ |
| Callback báo đã giao hoặc đã bắt máy | Không được coi là xác minh OTP thành công |
| Dịch vụ rủi ro hoặc kho hạn mức lỗi | Không mặc định bỏ kiểm soát để tiếp tục gọi |
| Tạo luồng mới hoặc đổi thiết bị | Giới hạn tổng hợp tài khoản, số nhận và chi phí vẫn còn hiệu lực |
| Có bằng chứng SMS và thoại cùng số | Không được tính thành hai yếu tố độc lập |
| Tuyến bị tắt do sự cố hoặc phát hiện lạm dụng | Công việc chưa gửi phải kiểm tra lại điều kiện; phương thức mạnh khác vẫn có thể dùng theo chính sách |

Theo dõi số yêu cầu fallback, lý do quyết định nội bộ, số cuộc gọi, tỷ lệ nhập mã thành công, độ trễ, chi phí và thay đổi phương thức sau khôi phục giúp nhận ra lỗi vận hành hoặc lạm dụng. Dùng tham chiếu nội bộ, che bớt số nhận và tránh ghi OTP hoặc token vào dữ liệu quan sát. Chính sách cần được xem lại khi cấu hình nhà cung cấp, tuyến vận hành hoặc mức nhạy cảm của tài khoản thay đổi để phương án dự phòng tiếp tục giữ đúng ranh giới xác minh.
