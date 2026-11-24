# Abuse response escalation

Một đợt tăng yêu cầu khôi phục có thể xuất phát từ lỗi ứng dụng, người dùng retry, bot gửi thư hàng loạt hoặc một chiến dịch chiếm tài khoản. Các tình huống này có thể tạo tín hiệu giống nhau nhưng cần phản ứng khác nhau.

**Abuse response escalation** là việc nâng mức ứng phó khi bằng chứng, tác động hoặc độ khẩn cấp thay đổi: từ quan sát và giới hạn cục bộ tới điều tra thủ công hoặc xử lý sự cố. Mục tiêu là ngăn thiệt hại với phạm vi phù hợp, giữ đường khôi phục cho người hợp lệ và tránh để kẻ tấn công điều khiển phản ứng của hệ thống.

Trong khôi phục tài khoản, phản ứng quá mạnh có thể gây hại trực tiếp. Nếu người chưa xác thực chỉ cần gửi nhiều request để hệ thống khóa đăng nhập hoặc thu hồi mọi session của nạn nhân, cơ chế phòng vệ đã trở thành một công cụ từ chối dịch vụ.

## 1. Tách nghi ngờ, tác động và bằng chứng sở hữu

Không nên dùng một nhãn “rủi ro cao” cho mọi quyết định. Cần phân biệt ít nhất ba câu hỏi:

1. Có cơ sở đến đâu để cho rằng hành vi đang gây hại?
2. Thiệt hại đang xảy ra hoặc có thể xảy ra nghiêm trọng đến mức nào?
3. Người đang yêu cầu khôi phục đã cung cấp bằng chứng nào về quyền kiểm soát tài khoản?

| Tín hiệu | Có thể hỗ trợ suy luận | Không tự chứng minh |
| --- | --- | --- |
| Nhiều request từ một mạng | Nguồn đang tạo tải bất thường | Tài khoản mục tiêu đã bị chiếm |
| Nhiều nguồn cùng nhắm một kênh nhận | Có chiến dịch gây ngập hoặc thử phân tán | Mọi session hiện tại đều thuộc kẻ tấn công |
| Nhiều lần nhập mã sai | Có khả năng đoán bằng chứng | Người dùng không còn quyền truy cập hợp lệ |
| Người dùng mất cookie hoặc đổi thiết bị | Ngữ cảnh chưa quen thuộc | Có hành vi độc hại |
| Báo cáo thay MFA trái phép qua kênh đã xác minh | Có căn cứ điều tra chiếm đoạt | Mọi chi tiết trong báo cáo đều đã được xác nhận |
| Bằng chứng về session bị đánh cắp | Có căn cứ cô lập session liên quan | Có thể bỏ qua xác minh trong giao dịch khôi phục khác |

Một điểm số chống bot không phải bằng chứng sở hữu. Việc có nhiều cảnh báo cũng không làm một hồ sơ hỗ trợ tự trở thành “đã xác minh”.

Tách các câu hỏi trên giúp chọn biện pháp phù hợp. Gửi thư hàng loạt có thể cần giảm tác dụng phụ của kênh gửi; bằng chứng session bị chiếm có thể cần quy trình cô lập quyền truy cập.

## 2. Xác định mục tiêu trước khi nâng mức

Mỗi quyết định nên nói rõ đang bảo vệ điều gì:

- **Kênh nhận của người dùng:** giảm email, SMS hoặc cuộc gọi không mong muốn.
- **Tài nguyên dịch vụ:** giữ queue, database, bộ xác minh và nhà cung cấp trong khả năng xử lý.
- **Bằng chứng khôi phục:** hạn chế đoán, phát lại hoặc chuyển bằng chứng sang giao dịch khác.
- **Quyền kiểm soát tài khoản:** chặn thay mật khẩu, MFA hoặc passkey trái phép.
- **Khả năng khôi phục hợp lệ:** tránh để chủ tài khoản bị chặn cùng với lưu lượng gây hại.

Không phải mọi mục tiêu đều cần thay đổi trạng thái tài khoản. Ví dụ, hạn chế gửi lại SMS không nhất thiết phải thu hồi session đang đăng nhập.

OWASP khuyến nghị tránh thay đổi tài khoản, chẳng hạn khóa tài khoản, trước khi có token hợp lệ trong luồng quên mật khẩu. Đây là một điểm tựa quan trọng khi thiết kế phản ứng trước yêu cầu công khai. Xem [Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).

## 3. Một mô hình mức ứng phó minh họa

Bảng sau là mô hình thiết kế cho bài học, không phải thang mức bắt buộc của một tiêu chuẩn:

| Mức | Tình huống phù hợp | Hành động có thể áp dụng | Điều cần bảo vệ |
| --- | --- | --- | --- |
| Quan sát | Tín hiệu yếu, chưa thấy tác động đáng kể | Tổng hợp sự kiện, theo dõi xu hướng, tăng dữ liệu chẩn đoán được phép | Không gây thêm khó khăn chỉ vì một tín hiệu đơn lẻ |
| Hạn chế cục bộ | Lạm dụng đã rõ ở nguồn, giao dịch hoặc tác dụng phụ | Giới hạn resend, gộp job, tăng yêu cầu tương tác hoặc dừng một giao dịch theo policy | Không mặc nhiên khóa toàn tài khoản |
| Điều tra có chủ sở hữu | Nhiều tín hiệu liên quan, ảnh hưởng kéo dài hoặc cần phân biệt chiếm đoạt | Giao hồ sơ cho nhóm phụ trách, xem bằng chứng và quyết định có thẩm quyền | Giữ tiêu chuẩn xác minh và giới hạn quyền của nhân viên |
| Ứng phó sự cố | Tác động rộng hoặc có bằng chứng nghiêm trọng cần phối hợp | Cô lập phạm vi bị ảnh hưởng, điều phối năng lực, xử lý credential hoặc session theo policy | Chỉ thực hiện thay đổi nhạy cảm với căn cứ và thẩm quyền phù hợp |

Các mức không phải một chuỗi buộc phải đi tuần tự. Một bằng chứng đáng tin về việc credential đang bị khai thác có thể cần chuyển trực tiếp sang quy trình sự cố. Ngược lại, hàng nghìn request bị từ chối mà không gây tác động không tự động đòi hỏi thu hồi session của hàng nghìn tài khoản.

Độ khẩn cấp cũng khác với mức tin cậy. Một đợt tiêu hao SMS rất nhanh có thể buộc hệ thống giảm gửi ngay để bảo vệ ngân sách, trong khi việc xác định ai đứng sau vẫn chưa rõ.

NIST SP 800-61 Rev. 3 đặt ứng phó sự cố trong hoạt động quản lý rủi ro, bao gồm chuẩn bị, phát hiện, ứng phó và phục hồi. Mô hình mức của bài này là một cách cụ thể hóa cho luồng khôi phục, không phải phân loại do NIST quy định. Tham khảo [NIST SP 800-61 Rev. 3](https://csrc.nist.gov/pubs/sp/800/61/r3/final).

## 4. Chọn phạm vi nhỏ nhất đủ để giảm hại

Trước khi nâng phạm vi, cần xác định tín hiệu gắn với thực thể nào:

~~~text
Một giao dịch
    → một tác dụng phụ hoặc kênh gửi
    → một nhóm nguồn hoặc một đích nhận
    → một tenant hoặc phân vùng dịch vụ
    → toàn bộ dịch vụ
~~~

Đây là các lựa chọn phạm vi, không phải thứ tự bắt buộc.

Ví dụ, nếu một nguồn đang thử mã trên một giao dịch, có thể dừng việc thử thêm trong giao dịch đó theo policy. Nếu nhiều nguồn làm ngập cùng một đích nhận, cần kiểm soát tổng số thông báo tới đích, thay vì chỉ chặn từng IP.

Khi nhà cung cấp SMS chậm trên diện rộng, tăng mức cảnh báo “tài khoản bị tấn công” cho mọi người dùng có thể sai. Trước hết cần phân biệt sự cố vận hành với lạm dụng và giới hạn việc retry gây khuếch đại.

Phạm vi toàn dịch vụ chỉ nên được chọn khi tác động hoặc giới hạn tài nguyên thực sự cần tới nó. Kèm theo đó phải có chủ sở hữu quyết định, cách theo dõi ảnh hưởng và kế hoạch giảm phạm vi khi điều kiện cho phép.

## 5. Định nghĩa điều kiện nâng mức bằng dữ liệu có ngữ cảnh

Một điều kiện nâng mức nên kết hợp:

- Loại hành vi và cửa sổ thời gian quan sát.
- Độ mới, độ tin cậy và nguồn của tín hiệu.
- Phạm vi thực thể bị ảnh hưởng.
- Tác động thực tế như số lần gửi, độ trễ hoặc thay đổi trái phép.
- Kết quả của biện pháp đang áp dụng.
- Chất lượng dữ liệu và những điều chưa biết.

Chỉ đếm số cảnh báo dễ tạo vòng lặp: một request sinh nhiều sự kiện, mỗi sự kiện lại làm mức nghiêm trọng tăng thêm. Cần chống trùng và liên kết sự kiện theo giao dịch hoặc chiến dịch, đồng thời vẫn giữ thông tin về các nguồn độc lập.

Các mẫu điều kiện minh họa:

| Quan sát tổng hợp | Hướng ứng phó có thể phù hợp |
| --- | --- |
| Lưu lượng bất thường nhưng số lần gửi và độ trễ vẫn được kiểm soát | Tiếp tục quan sát, xem hiệu quả giới hạn hiện tại |
| Nhiều nguồn khiến số lần gửi thực tế vượt ngân sách của một kênh | Hạn chế tác dụng phụ và giao trách nhiệm điều tra |
| Người dùng hợp lệ liên tục bị chặn sau một thay đổi policy | Điều tra chính sách hoặc vận hành, không tự kết luận có thêm tấn công |
| Báo cáo đã xác minh kết hợp với dấu vết thay authenticator ngoài ý muốn | Chuyển quy trình điều tra chiếm đoạt tài khoản |
| Lạm dụng làm queue hoặc nhà cung cấp gần cạn năng lực | Phối hợp ứng phó sự cố ở phạm vi tài nguyên bị ảnh hưởng |

Ngưỡng số cụ thể cần được sản phẩm xác định từ lưu lượng và mức chấp nhận rủi ro. Mức tin cậy của dữ liệu thấp không nên bị che bởi một con số điểm rủi ro trông có vẻ chính xác.

## 6. Ghi quyết định thành một đối tượng có thể theo dõi

Không nên chỉ lưu “đã nâng lên mức cao”. Một quyết định cần đủ thông tin để biết lý do, phạm vi và hiệu lực.

Mô hình khái niệm:

~~~text
AbuseResponseDecision
  decisionId
  policyVersion
  scopeType
  scopeReference
  evidenceReferences
  reasonCode
  action
  authority
  owner
  createdAt
  reviewAt
  expiresAt
  expectedStateVersion
  applicationState
  resultReference
~~~

Ý nghĩa của một số trường:

**Evidence references:** trỏ tới dữ liệu nội bộ đã được bảo vệ, thay vì sao chép token hoặc toàn bộ phản hồi xác thực vào hồ sơ.

**Authority:** cho biết hành động thuộc policy tự động đã được phê duyệt hay một quyết định thủ công có thẩm quyền. Một công cụ chấm điểm không tự có quyền làm mọi thay đổi nhạy cảm.

**Owner:** xác định ai chịu trách nhiệm tiếp nhận, đánh giá và kết thúc biện pháp. Chuyển vào một queue không có người phụ trách không đồng nghĩa đã xử lý.

**Review và expiry:** quy định khi nào cần xem lại và giới hạn tồn tại của biện pháp tạm thời. Không phải mọi loại cô lập đều nên tự hết hạn; trường hợp credential đã xác định bị chiếm cần điều kiện phục hồi phù hợp.

**Application state:** phân biệt quyết định được đề xuất, đang thực hiện, đã áp dụng và thất bại. Gửi một lệnh vào queue chưa phải bằng chứng biện pháp đã có hiệu lực.

Trạng thái quyết định ứng phó nên được tách khỏi trạng thái xác minh chủ tài khoản. Nâng mức điều tra không được làm giao dịch tự chuyển sang “đủ quyền thay MFA”.

## 7. Thực thi quyết định mà không tạo thay đổi lặp hoặc lỗi thời

Trong hệ thống nhiều instance, cùng một chiến dịch có thể tạo nhiều quyết định gần như đồng thời. Ngoài việc chống trùng cảnh báo, cần bảo vệ hành động thực thi.

Luồng minh họa:

~~~mermaid
flowchart TD
    A["Tổng hợp tín hiệu"] --> B["Đánh giá policy và tác động"]
    B --> C["Tạo quyết định với phạm vi, thẩm quyền và phiên bản"]
    C --> D["Kiểm tra trạng thái hiện tại"]
    D --> E["Áp dụng hành động có kiểm soát đồng thời"]
    E --> F["Ghi kết quả thực tế"]
    F --> G["Theo dõi ảnh hưởng và thời điểm xem lại"]
    G --> H["Giữ, sửa phạm vi hoặc kết thúc theo điều kiện"]
~~~

Các nguyên tắc thực thi trong thiết kế này:

- Dùng ID quyết định hoặc ID thao tác để tránh lặp cùng tác dụng phụ khi retry.
- Kiểm tra phiên bản trạng thái trước khi áp dụng thay đổi đã được tạo từ dữ liệu cũ.
- Không để một quyết định tự động đến trễ ghi đè một quyết định thủ công mới hơn.
- Ghi nhận lỗi thực thi; không báo “đã cô lập” nếu lệnh chưa thành công.
- Khi hết hạn, chỉ gỡ phần hạn chế do quyết định đó tạo ra, không xóa mọi hạn chế đang tồn tại.

Ví dụ, một bộ hẹn giờ muốn gỡ hạn chế gửi cũ phải xác nhận rằng nó vẫn đang sở hữu hạn chế tương ứng. Nếu nhân viên đã đặt một biện pháp khác có căn cứ mới, bộ hẹn giờ không được vô tình gỡ luôn biện pháp đó.

Nếu hành động đi qua hệ thống bên ngoài, cần theo dõi kết quả và xử lý trạng thái chưa rõ. Không giả định timeout đồng nghĩa với hành động chưa xảy ra rồi lặp lại vô hạn.

## 8. Điều tra thủ công không được trở thành đường tắt

Nâng mức sang con người có ích khi tín hiệu tự động chưa đủ để phân biệt lạm dụng, lỗi vận hành và nhu cầu khôi phục thật. Nhưng áp lực hỗ trợ cũng là một bề mặt bị khai thác.

Một bàn giao có ích cần nêu:

- Tác động đã quan sát được và phạm vi bị ảnh hưởng.
- Bằng chứng có sẵn, độ tin cậy và những điểm chưa xác nhận.
- Biện pháp đã áp dụng cùng kết quả.
- Trạng thái xác minh của người yêu cầu.
- Quyết định tiếp theo cần người có thẩm quyền thực hiện.
- Thời điểm xem lại và người chịu trách nhiệm.

Nhân viên không nên được yêu cầu đọc OTP, token khôi phục hoặc mã dự phòng trong hội thoại chỉ để “xác nhận nhanh”. Cần dùng quy trình tiếp nhận bằng chứng đã thiết kế, với quyền truy cập phù hợp.

Một hồ sơ có nhiều tin nhắn khẩn cấp không tự có ưu tiên bảo mật cao hơn. Nếu việc gây ngập ticket giúp được bỏ qua bước xác minh, escalation đã trở thành một cách hạ mức bảo đảm.

Đối với thao tác nhạy cảm như thay kênh khôi phục hoặc gỡ MFA, quyền của nhân viên cần được giới hạn theo vai trò và policy. Khi sản phẩm quy định thêm người kiểm soát hoặc phê duyệt, quy trình điều tra phải giữ điều kiện đó.

## 9. Bảo vệ đường khôi phục của người hợp lệ

Người thật vừa mất thiết bị thường thiếu cookie, lịch sử trình duyệt và khả năng trả lời challenge trên thiết bị cũ. Đây cũng là các tín hiệu có thể khiến hệ thống tự động nghi ngờ.

Biện pháp ứng phó cần phân biệt giữa:

- Ngăn tạo thêm tác dụng phụ, như gửi hàng loạt SMS.
- Ngăn thử bằng chứng không giới hạn.
- Dừng một giao dịch có vấn đề.
- Thay đổi quyền truy cập hoặc trạng thái tài khoản.

Không được coi bốn hành động này là tương đương.

Khi hạn chế resend, người đang có bằng chứng hợp lệ vẫn nên có đường tiếp tục theo policy nếu điều kiện cho phép. Đường đó vẫn cần chống đoán, kiểm tra hết hạn và tiêu thụ bằng chứng đúng cách; nó không phải một ngoại lệ bỏ qua bảo mật.

Hướng dẫn công khai cần cho biết bước tiếp theo có thể thực hiện. Ví dụ:

~~~text
Chưa thể gửi thêm hướng dẫn vào lúc này.
Nếu bạn đã nhận được hướng dẫn, hãy tiếp tục theo thông tin đó.
Bạn cũng có thể dùng quy trình hỗ trợ chính thức.
~~~

Thông báo phải phù hợp với ngữ cảnh mà người dùng được phép biết. Trên điểm vào chưa xác thực, tránh tiết lộ rằng một email cụ thể đang bị điều tra hoặc có tài khoản tồn tại.

Các kênh hỗ trợ thay thế cũng cần năng lực và kiểm soát lạm dụng. Chuyển toàn bộ lưu lượng bị chặn sang một queue thủ công không giới hạn chỉ tạo một điểm nghẽn mới.

## 10. Thông báo đúng mục đích và tránh khuếch đại

Thông báo có thể phục vụ các mục đích khác nhau:

| Loại thông báo | Mục đích | Yêu cầu thiết kế |
| --- | --- | --- |
| Hướng dẫn cho người đang khôi phục | Giúp biết bước tiếp theo | Không lộ ngưỡng hoặc công thức phát hiện |
| Cảnh báo bảo mật cho chủ tài khoản | Nhận biết và phản hồi thay đổi đáng ngờ | Dùng kênh đã thiết lập còn phù hợp với mức tin cậy |
| Thông tin vận hành nội bộ | Điều phối ứng phó | Có chủ sở hữu, phạm vi và liên kết bằng chứng |
| Thông tin về gián đoạn dịch vụ | Giải thích ảnh hưởng diện rộng | Không công khai danh sách tài khoản bị nhắm |

Không gửi một email cảnh báo cho mỗi request bị chặn. Đợt lạm dụng có thể biến cơ chế cảnh báo thành một công cụ làm ngập thứ hai. Có thể gộp sự kiện tương tự và giới hạn tần suất theo policy.

Tuy nhiên, không nên gộp mù quáng đến mức mất thông báo về một thay đổi bảo mật quan trọng đã thực sự xảy ra. Cảnh báo thử thất bại và thông báo thay phương thức xác thực có ý nghĩa khác nhau.

Nếu kênh khôi phục có dấu hiệu bị chiếm, không mặc nhiên coi kênh đó là nơi an toàn để gửi mọi chỉ dẫn nhạy cảm. Việc chọn kênh cần dựa vào bằng chứng và chính sách của tình huống, không lấy địa chỉ mới do người đang gọi tự cung cấp làm nơi tin cậy.

## 11. Hạ mức và phục hồi là một phần của quyết định

Một biện pháp tạm thời thiếu điều kiện kết thúc có thể giữ người dùng trong trạng thái bị hạn chế rất lâu sau khi lạm dụng đã dừng.

Trước khi áp dụng, cần xác định:

- Dấu hiệu nào cho phép giảm mức hoặc phạm vi.
- Khoảng quan sát ổn định cần thiết theo policy.
- Ai có quyền kết thúc biện pháp.
- Những thay đổi nào có thể đảo ngược an toàn.
- Trạng thái nào cần được xác minh lại trước khi khôi phục hoạt động.

Có thể dùng điều kiện nâng và hạ khác nhau để tránh liên tục bật tắt quanh một ngưỡng. Đây là ý tưởng hysteresis: một dao động ngắn không làm hệ thống đổi chế độ nhiều lần.

Hết thời hạn hạn chế gửi không có nghĩa credential đã xác định bị đánh cắp trở lại an toàn. Tương tự, lưu lượng giảm có thể là dấu hiệu bên gây hại tạm dừng, không phải bằng chứng chủ tài khoản đã được xác minh.

Khi hạ mức, không tự khôi phục session đã thu hồi, token đã dùng hoặc phương thức xác thực đã bị loại vì bị chiếm. Phục hồi dịch vụ và khôi phục quyền kiểm soát tài khoản là các quyết định liên quan nhưng khác nhau.

Cần xem cả dấu hiệu tác dụng phụ: tỷ lệ người hợp lệ hoàn tất, số yêu cầu hỗ trợ, thời gian chờ và số thông báo thực sự được gửi. Lưu lượng giảm do mọi người đều bị chặn không phải kết quả tốt một cách mặc nhiên.

## 12. Ví dụ: từ làm ngập email tới điều tra thay MFA

Linh mất điện thoại và bắt đầu khôi phục. Một đợt lưu lượng phân tán cùng lúc nhắm vào email của cô.

**Giai đoạn đầu:** hệ thống thấy số lần gửi tăng nhưng chưa có bằng chứng tài khoản bị chiếm. Biện pháp phù hợp là hạn chế tác dụng phụ của kênh gửi, chống trùng job và quan sát. Việc thu hồi mọi session của Linh chỉ dựa trên số request sẽ trao cho người ngoài quyền gây gián đoạn.

**Khi tác động kéo dài:** nhóm phụ trách nhận hồ sơ có phạm vi rõ ràng, dữ liệu gửi thực tế và trạng thái policy. Họ xác định liệu giới hạn đang bị bỏ qua qua một endpoint khác hay nhà cung cấp đang retry bất thường. Đây vẫn chưa tự là bằng chứng ai đang kiểm soát tài khoản.

**Khi xuất hiện bằng chứng mới:** Linh báo qua một kênh được xác minh rằng MFA đã bị thay trái phép, và dữ liệu hệ thống cho thấy thay đổi liên quan. Vụ việc chuyển sang quy trình điều tra chiếm đoạt. Người có thẩm quyền quyết định cô lập các quyền hoặc phương thức bị xác định có vấn đề theo policy, đồng thời giữ quy trình xác minh để khôi phục quyền cho Linh.

**Khi kết thúc:** biện pháp hạn chế gửi được xem lại theo điều kiện của nó. Những credential đã bị xác định bị chiếm không được tự bật lại chỉ vì chiến dịch gửi email đã dừng. Hồ sơ ghi rõ hành động thực tế, phần còn chưa chắc chắn và chủ sở hữu công việc phục hồi.

Điểm quyết định trong ví dụ là bằng chứng và tác động đã thay đổi, nên phạm vi ứng phó cũng thay đổi. Escalation bảo vệ luồng khôi phục khi mỗi bước đều có mục tiêu, thẩm quyền và điều kiện kết thúc, thay vì chỉ tăng độ nghiêm khắc theo số lượng cảnh báo.
