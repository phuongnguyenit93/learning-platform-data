# Kết hợp đánh giá khả năng sử dụng với người dùng đại diện

Khả năng sử dụng (usability) cho biết người dùng có thể hiểu và hoàn thành mục tiêu của mình với sản phẩm dễ dàng, hiệu quả và ít sai sót đến mức nào. Một chức năng có thể đáp ứng đúng yêu cầu kỹ thuật nhưng vẫn khó dùng: người dùng không nhận ra bước tiếp theo, hiểu sai trạng thái, mắc lỗi lặp lại hoặc cần nhờ hỗ trợ để hoàn tất tác vụ. Vì vậy, kiểm thử chức năng và đánh giá khả năng sử dụng cần được kết hợp để xem xét cả tính đúng đắn của hệ thống lẫn trải nghiệm thực tế.

Đánh giá với người dùng đại diện (representative users) giúp nhóm quan sát cách những người có đặc điểm, mục tiêu và bối cảnh sử dụng phù hợp tương tác với sản phẩm. Người tham gia thực hiện các tác vụ có ý nghĩa trong khi nhóm ghi nhận hành vi, khó khăn, thời gian, lỗi và phản hồi. Kết quả giúp xác định vấn đề mà nhóm thiết kế hoặc phát triển có thể không nhận ra khi chỉ tự kiểm tra sản phẩm.

Đây là một hoạt động kiểm thử phi chức năng. Nó bổ sung bằng chứng về hiệu quả hoàn thành tác vụ, mức độ dễ học, khả năng ghi nhớ, khả năng phòng tránh và phục hồi lỗi, sự hài lòng và khả năng tiếp cận. Kết quả nên được dùng để cải thiện sản phẩm và kiểm chứng lại sau thay đổi, không chỉ để thu thập ý kiến chung về giao diện.

## 1. Hiểu khả năng sử dụng và vai trò của người dùng đại diện

### Khả năng sử dụng là gì?

Khả năng sử dụng mô tả mức độ mà một nhóm người dùng xác định có thể đạt mục tiêu xác định trong một bối cảnh sử dụng cụ thể với hiệu quả, hiệu suất và sự hài lòng phù hợp. Ba khía cạnh thường được xem xét là:

- **Hiệu quả (effectiveness):** người dùng có hoàn thành đúng mục tiêu và tạo ra kết quả chính xác không?
- **Hiệu suất (efficiency):** họ cần bao nhiêu thời gian, bước thao tác, công sức hoặc trợ giúp để hoàn thành?
- **Sự hài lòng (satisfaction):** họ cảm thấy dễ hiểu, tự tin và thoải mái đến mức nào khi sử dụng?

Nhóm cũng cần quan tâm đến khả năng học cách sử dụng (learnability), khả năng ghi nhớ sau một thời gian không sử dụng (memorability), khả năng phòng tránh và phục hồi lỗi (error prevention and recovery), cũng như khả năng tiếp cận (accessibility). Các khía cạnh này có thể quan trọng khác nhau theo sản phẩm và nhóm người dùng.

Ví dụ, với một hệ thống kê khai thuế, hiệu quả có thể là người dùng gửi đúng hồ sơ và không bỏ sót thông tin bắt buộc; hiệu suất có thể là thời gian hoàn thành và số lần phải sửa; sự hài lòng có thể phản ánh mức độ tự tin rằng hồ sơ đã được gửi thành công. Với ứng dụng hỗ trợ nhân viên kho, khả năng sử dụng trong điều kiện đeo găng tay, màn hình nhỏ hoặc mạng chập chờn có thể quan trọng hơn một giao diện có nhiều tùy chọn.

### Vì sao cần người dùng đại diện?

Nhóm phát triển thường hiểu thuật ngữ, cấu trúc và giả định của sản phẩm quá rõ. Họ có thể hoàn thành một luồng mà người mới không hiểu, hoặc bỏ qua khó khăn mà người dùng gặp trong môi trường thực tế. Người dùng đại diện giúp kiểm tra xem thiết kế có phù hợp với mục tiêu, kiến thức, khả năng và bối cảnh sử dụng của nhóm mà sản phẩm phục vụ hay không.

“Đại diện” không có nghĩa là tìm một người giống hệt mọi người dùng. Đó là việc tuyển người có các đặc điểm liên quan đến câu hỏi đánh giá, chẳng hạn:

- Vai trò và quyền hạn khi sử dụng sản phẩm.
- Mức độ kinh nghiệm với nghiệp vụ hoặc công nghệ.
- Tần suất và mức độ quan trọng của tác vụ.
- Thiết bị, trình duyệt, mạng và môi trường làm việc.
- Ngôn ngữ, khả năng đọc hiểu và nhu cầu hỗ trợ.
- Khả năng vận động, thị giác, thính giác, nhận thức hoặc việc sử dụng công nghệ trợ giúp khi phù hợp.
- Những khác biệt giữa người dùng mới, người dùng thường xuyên và người dùng chuyên sâu.

Một người dùng đại diện cho nhóm quản trị viên có thể không đại diện cho khách hàng mới. Người dùng thành thạo máy tính có thể không phản ánh trải nghiệm của người ít kinh nghiệm. Cần xác định rõ nhóm nào và bối cảnh nào đang được đánh giá.

### Phân biệt đánh giá khả năng sử dụng với khảo sát ý kiến

Khảo sát có thể hỏi người dùng họ thích giao diện nào hoặc cảm thấy sản phẩm ra sao. Đánh giá khả năng sử dụng quan sát người dùng thực hiện tác vụ và thu thập bằng chứng về những gì họ làm, nơi họ gặp khó khăn và kết quả đạt được.

Một người có thể nói giao diện “dễ dùng” nhưng vẫn mất nhiều thời gian hoặc mắc lỗi khi thực hiện tác vụ. Ngược lại, họ có thể không thích màu sắc nhưng vẫn hoàn thành công việc chính xác. Vì vậy, nên kết hợp quan sát hành vi với câu hỏi sau tác vụ và thang đo phù hợp, tránh coi ý kiến tự báo cáo là bằng chứng duy nhất.

## 2. Xác định mục tiêu và phạm vi đánh giá

Trước khi tuyển người tham gia, nhóm cần biết mình muốn kiểm chứng điều gì. Mục tiêu rõ giúp chọn đúng người, tác vụ, môi trường và chỉ số. Nếu mục tiêu quá rộng như “đánh giá giao diện”, kết quả dễ trở thành danh sách ý kiến rời rạc mà không dẫn đến quyết định cụ thể.

### Bắt đầu từ người dùng và tác vụ

Xác định các nhóm người dùng quan trọng, việc họ cần hoàn thành và bối cảnh thực hiện. Có thể sử dụng persona, hành trình người dùng, quy trình nghiệp vụ, dữ liệu hỗ trợ và nghiên cứu trước đó làm đầu vào. Persona nên dựa trên bằng chứng và mô tả mục tiêu, hành vi, nhu cầu; không nên biến thành khuôn mẫu thiếu căn cứ.

Với mỗi tác vụ, ghi nhận:

- Mục tiêu người dùng muốn đạt.
- Điểm bắt đầu và điều kiện cần có.
- Các bước hoặc quyết định quan trọng.
- Kết quả được coi là hoàn thành đúng.
- Các trường hợp thay thế và lỗi có thể xảy ra.
- Mức độ quan trọng, tần suất và hậu quả nếu thất bại.
- Bối cảnh thiết bị, môi trường và ràng buộc thực tế.

Ví dụ với cổng dịch vụ khách hàng, các tác vụ có thể là tìm hóa đơn, cập nhật địa chỉ nhận hàng, gửi yêu cầu hoàn tiền và kiểm tra trạng thái xử lý. Tác vụ hoàn tiền có thể ít xảy ra hơn việc tìm hóa đơn nhưng hậu quả khi người dùng gửi sai yêu cầu hoặc không biết giao dịch đã được tiếp nhận có thể lớn hơn.

### Viết mục tiêu đánh giá có thể kiểm chứng

Mục tiêu nên chỉ rõ nhóm người dùng, tác vụ và kết quả cần quan sát. Ví dụ:

- Người dùng mới có thể tạo tài khoản và xác minh email mà không cần trợ giúp.
- Nhân viên kho có thể xác nhận xuất hàng trên thiết bị cầm tay trong điều kiện mạng không ổn định.
- Khách hàng có thể nhận biết rõ đơn hàng đang chờ thanh toán hay đã thanh toán.
- Người dùng bàn phím có thể hoàn thành luồng gửi biểu mẫu mà không cần thao tác chuột.

Sau đó, chọn chỉ số và tiêu chí chấp nhận phù hợp. Không nên đặt ngưỡng trước khi hiểu nhu cầu và có dữ liệu nền. Nếu chưa có dữ liệu, buổi đánh giá đầu tiên có thể dùng để khám phá vấn đề và xây dựng mức tham chiếu.

### Ưu tiên theo rủi ro

Ưu tiên các tác vụ có tần suất cao, ảnh hưởng lớn đến mục tiêu nghiệp vụ, liên quan đến dữ liệu hoặc tiền, có hậu quả khó phục hồi hoặc từng gây nhiều yêu cầu hỗ trợ. Xem xét cả nhóm người dùng dễ bị bỏ sót, vì một luồng có vẻ đơn giản với đa số vẫn có thể tạo rào cản lớn cho người sử dụng công nghệ trợ giúp.

## 3. Tuyển chọn người tham gia đại diện

Chất lượng đánh giá phụ thuộc nhiều vào việc tuyển đúng người. Số lượng người tham gia không thể bù cho việc chọn sai nhóm hoặc bỏ sót bối cảnh sử dụng quan trọng.

### Xây dựng tiêu chí tuyển chọn

Lập tiêu chí theo mục tiêu nghiên cứu. Ví dụ, nếu đánh giá quy trình quản lý kho, cần người thực sự thực hiện nhận hàng, kiểm đếm hoặc xuất hàng; không chỉ tuyển người làm việc trong ngành nhưng không dùng quy trình đó. Nếu đánh giá ứng dụng tài chính cá nhân, cần phân biệt người mới với người thường xuyên quản lý nhiều tài khoản.

Một bảng tuyển chọn có thể gồm:

| Tiêu chí | Nhóm cần có | Lý do |
|---|---|---|
| Vai trò | Người thực hiện nghiệp vụ chính và người phê duyệt nếu có | Kiểm tra luồng theo quyền và trách nhiệm khác nhau |
| Kinh nghiệm | Người mới và người dùng thường xuyên | Phát hiện vấn đề học cách dùng và hiệu quả của người thành thạo |
| Tần suất sử dụng | Dùng hằng ngày, thỉnh thoảng hoặc theo sự kiện | Quan sát khác biệt về ghi nhớ và mức độ quen thuộc |
| Thiết bị | Thiết bị thực tế được hỗ trợ | Xác minh giao diện và thao tác trong bối cảnh đích |
| Khả năng tiếp cận | Người dùng công nghệ trợ giúp khi mục tiêu liên quan | Tìm rào cản mà kiểm tra tự động hoặc người không có nhu cầu đó có thể bỏ sót |
| Bối cảnh | Môi trường làm việc, mạng và ngôn ngữ liên quan | Đánh giá tác động của điều kiện thực tế |

Tiêu chí cần tránh thu thập thông tin nhạy cảm không cần thiết. Chỉ hỏi những đặc điểm liên quan đến câu hỏi đánh giá và giải thích cách dữ liệu tuyển chọn được sử dụng.

### Chọn phương pháp lấy mẫu

Với đánh giá định tính khám phá, lấy mẫu có chủ đích (purposive sampling) thường phù hợp: chọn người có kinh nghiệm hoặc đặc điểm giúp làm rõ vấn đề. Với khảo sát định lượng hoặc nghiên cứu cần ước lượng tỷ lệ cho một quần thể, cần thiết kế mẫu và kích thước mẫu theo mục tiêu thống kê, độ biến thiên và mức tin cậy mong muốn.

Không có một con số người tham gia cố định phù hợp cho mọi buổi đánh giá. Một số vòng nghiên cứu khả năng sử dụng định tính có thể bắt đầu với nhóm nhỏ, sau đó tuyển thêm người khi xuất hiện nhóm người dùng hoặc vấn đề mới. Nghiên cứu định lượng cần cỡ mẫu được tính toán theo câu hỏi, chỉ số, mức chênh lệch cần phát hiện và phương pháp phân tích. Không nên lấy quy tắc “năm người là đủ” làm tiêu chuẩn phổ quát.

### Sàng lọc và mời tham gia

Sử dụng câu hỏi sàng lọc ngắn để xác định người tham gia phù hợp với tiêu chí. Tránh mô tả quá chi tiết giải pháp hoặc câu trả lời mong muốn, vì điều đó có thể khiến người tham gia chuẩn bị trước và làm sai lệch hành vi quan sát.

Khi mời tham gia, cung cấp mục đích chung, thời lượng, hình thức trực tiếp hay từ xa, yêu cầu thiết bị, khoản hỗ trợ nếu có, cách ghi âm/ghi hình và quyền dừng tham gia. Hỗ trợ chi phí hoặc thù lao nên công bằng, minh bạch và không tạo áp lực buộc người tham gia phải hoàn tất.

## 4. Thiết kế kịch bản và tác vụ đánh giá

Tác vụ là phần trung tâm của buổi đánh giá. Một tác vụ tốt mô tả mục tiêu bằng ngôn ngữ tự nhiên, đủ bối cảnh để người tham gia hiểu tình huống nhưng không hướng dẫn họ nhấn vào nút hoặc đi theo đường cụ thể.

### Viết tác vụ trung lập

Ví dụ không tốt: “Nhấn nút ‘Tạo yêu cầu hoàn tiền’ ở góc trên, chọn đơn hàng 123 rồi gửi.” Cách viết này tiết lộ giao diện và đường đi mong đợi, khiến buổi đánh giá kiểm tra khả năng làm theo hướng dẫn thay vì khả năng tự tìm cách hoàn thành.

Ví dụ tốt hơn: “Bạn nhận được một đơn hàng nhưng sản phẩm giao đến bị hư hỏng. Hãy tìm cách yêu cầu hoàn tiền cho đơn hàng đó và cho biết khi nào bạn nghĩ yêu cầu đã được gửi thành công.” Tác vụ cung cấp mục tiêu và bối cảnh, đồng thời cho phép quan sát cách người dùng tìm chức năng và hiểu trạng thái.

Tác vụ nên:

- Bắt đầu từ tình huống thực tế và mục tiêu cụ thể.
- Tránh dùng chính thuật ngữ hoặc tên nút mà giao diện đang sử dụng nếu mục tiêu là kiểm tra khả năng tìm thấy.
- Không chứa gợi ý từng bước hoặc câu trả lời.
- Có điều kiện hoàn thành quan sát được.
- Bao gồm trường hợp bình thường và một số tình huống có rủi ro.
- Có thể thực hiện trong thời gian phù hợp với buổi đánh giá.

### Bao phủ luồng chính và luồng ngoại lệ

Không chỉ kiểm tra đường đi lý tưởng. Người dùng có thể nhập sai, đổi ý, quay lại, mất kết nối, không có đủ thông tin hoặc hiểu nhầm trạng thái. Hãy chọn ngoại lệ có ý nghĩa với mục tiêu và hậu quả nghiệp vụ.

Ví dụ với tác vụ cập nhật địa chỉ:

1. Tìm đơn hàng đang chờ giao.
2. Xác định liệu địa chỉ còn có thể thay đổi hay không.
3. Cập nhật địa chỉ mới nếu hệ thống cho phép.
4. Xác nhận thay đổi đã được lưu và hiểu tác động đến lịch giao hàng.

Một kịch bản bổ sung có thể cung cấp địa chỉ thiếu mã bưu chính hoặc thử cập nhật sau khi đơn đã chuyển sang trạng thái không cho phép sửa. Mục tiêu là quan sát liệu thông báo lỗi và trạng thái tiếp theo có rõ ràng không.

### Chuẩn bị trạng thái và dữ liệu

Mỗi tác vụ cần trạng thái ban đầu rõ ràng: tài khoản, vai trò, dữ liệu, thiết bị và môi trường. Dữ liệu phải đủ thực tế để người tham gia hiểu bối cảnh nhưng không chứa thông tin thật không cần thiết. Có thể dùng tài khoản thử nghiệm và dữ liệu tổng hợp với tên, số tiền, ngày tháng và trạng thái hợp lý.

Nếu người tham gia thực hiện nhiều tác vụ, cân nhắc thứ tự để tránh một tác vụ làm thay đổi trạng thái ảnh hưởng đến tác vụ sau. Có thể dùng tài khoản hoặc bộ dữ liệu riêng cho từng người. Với nghiên cứu so sánh hai thiết kế, cần kiểm soát thứ tự và hiệu ứng học tập bằng cách cân bằng thứ tự trải nghiệm.

## 5. Chọn phương pháp đánh giá phù hợp

Có nhiều cách thu thập bằng chứng. Không có phương pháp nào phù hợp cho mọi câu hỏi; có thể kết hợp quan sát, đo lường và tự báo cáo để hiểu cả hành vi lẫn cảm nhận.

### Kiểm thử có điều phối (moderated usability testing)

Người điều phối hướng dẫn buổi đánh giá, đọc kịch bản, quan sát và đặt câu hỏi làm rõ mà không chỉ đường. Phương pháp này hữu ích khi cần hiểu lý do người tham gia hành động, thử nghiệm luồng phức tạp hoặc khám phá vấn đề mới.

Người điều phối nên:

- Giải thích rằng nhóm đang kiểm tra sản phẩm, không kiểm tra năng lực của người tham gia.
- Đọc tác vụ theo cùng một cách cho các phiên để giảm sai lệch.
- Khuyến khích người tham gia nói ra điều họ đang nghĩ nếu phương pháp yêu cầu think-aloud.
- Tránh gợi ý hoặc sửa lỗi thay người tham gia quá sớm.
- Đặt câu hỏi trung lập như “Bạn đang mong đợi điều gì sẽ xảy ra?” thay vì “Bạn có thấy nút này không?”.
- Ghi nhận hành vi và lời nói riêng biệt, phân biệt quan sát với diễn giải.

### Kiểm thử không điều phối (unmoderated testing)

Người tham gia tự thực hiện tác vụ theo hướng dẫn trong công cụ nghiên cứu. Phương pháp này có thể thu thập dữ liệu từ nhiều người hơn, giảm thời gian điều phối và hỗ trợ thử nghiệm từ xa. Tuy nhiên, nhóm khó hỏi thêm khi có hành vi bất ngờ và cần thiết kế hướng dẫn thật rõ để tránh hiểu sai.

Nên dùng khi tác vụ tương đối độc lập, có tiêu chí hoàn thành rõ và môi trường có thể kiểm soát. Cần kiểm tra thiết bị, chất lượng kết nối và cách ghi nhận thời gian trước khi triển khai rộng.

### Quan sát tại bối cảnh thực tế

Quan sát theo ngữ cảnh (contextual inquiry) hoặc nghiên cứu thực địa giúp hiểu môi trường làm việc, công cụ phụ trợ, gián đoạn và quy trình thực tế. Ví dụ, nhân viên kho có thể phải sử dụng ứng dụng trong khi di chuyển, đeo găng hoặc xử lý nhiều đơn đồng thời. Những điều kiện này khó tái hiện đầy đủ trong phòng lab.

Khi quan sát, hãy xin phép trước, tránh làm gián đoạn công việc và ghi nhận yếu tố bối cảnh ảnh hưởng đến hành vi. Nếu không thể đến môi trường thực, có thể mô phỏng các điều kiện liên quan và ghi rõ giới hạn.

### Đánh giá chuyên gia và kiểm tra khả năng tiếp cận

Đánh giá heuristic do chuyên gia sử dụng các nguyên tắc khả năng sử dụng để rà soát giao diện. Kiểm tra khả năng tiếp cận có thể kết hợp công cụ tự động, kiểm tra thủ công bằng bàn phím và trình đọc màn hình, cùng đánh giá với người dùng có nhu cầu tiếp cận liên quan.

Đánh giá chuyên gia hữu ích để tìm vấn đề nhanh, nhưng không thay thế quan sát người dùng đại diện. Công cụ accessibility tự động có thể phát hiện một số lỗi cấu trúc nhưng không thể đánh giá đầy đủ liệu nội dung, thứ tự thao tác và phản hồi có dễ hiểu trong tác vụ thật hay không.

### Kết hợp với khảo sát và phân tích hành vi

Sau tác vụ, có thể hỏi mức độ khó, tự tin hoặc hài lòng. Các thang đo như System Usability Scale (SUS) hoặc Single Ease Question (SEQ) có thể dùng khi phù hợp với mục tiêu và được triển khai theo hướng dẫn của thang đo. Không nên tự ý sửa câu hỏi hoặc so sánh điểm số giữa các nghiên cứu có cách dùng khác nhau mà không giải thích.

Phân tích hành vi sản phẩm, tỷ lệ bỏ dở, tìm kiếm hỗ trợ và ticket chăm sóc khách hàng có thể cho biết vấn đề phổ biến ở quy mô lớn. Dữ liệu này cho biết điều gì đang xảy ra trên diện rộng nhưng thường không giải thích đầy đủ vì sao. Kết hợp dữ liệu hành vi với quan sát trực tiếp giúp tạo bức tranh rõ hơn.

## 6. Đo lường hiệu quả sử dụng

Chỉ số cần phản ánh mục tiêu tác vụ. Không phải mọi tác vụ đều nên đo cùng một cách. Với thao tác quan trọng, hoàn thành sai có thể nghiêm trọng hơn mất thêm vài giây; với thao tác lặp lại thường xuyên, thời gian và số bước có thể có tác động lớn đến năng suất.

### Tỷ lệ hoàn thành tác vụ

Tỷ lệ hoàn thành (task completion rate) cho biết bao nhiêu người hoàn thành đúng tác vụ theo tiêu chí đã xác định. Cần phân biệt hoàn thành thành công độc lập, hoàn thành sau trợ giúp và không hoàn thành. Một người đến đúng màn hình nhưng không hiểu liệu yêu cầu đã được gửi hay chưa không nên được tính là hoàn thành đầy đủ nếu mục tiêu bao gồm xác nhận trạng thái.

### Thời gian hoàn thành

Thời gian tác vụ (time on task) đo khoảng thời gian từ mốc bắt đầu đã định đến khi đạt tiêu chí hoàn thành. Cần ghi rõ có tính thời gian đọc hướng dẫn, thời gian gián đoạn và thời gian trợ giúp hay không. So sánh nên dùng tác vụ, trạng thái ban đầu và điều kiện tương đương.

Thời gian ngắn hơn không luôn tốt hơn. Người dùng có thể hoàn thành nhanh vì bỏ qua bước kiểm tra quan trọng. Với thao tác tài chính hoặc y tế, thời gian dài hơn một chút để xác nhận đúng có thể là hành vi an toàn.

### Tỷ lệ lỗi và mức độ nghiêm trọng

Ghi nhận lỗi thao tác, bước sai, dữ liệu nhập sai, hành động không thể hoàn tác và nhu cầu nhờ trợ giúp. Phân biệt lỗi nhỏ có thể tự sửa với lỗi làm mất dữ liệu, gửi nhầm yêu cầu hoặc tạo hậu quả tài chính. Một chỉ số tổng hợp số lần nhấp sai có thể che giấu khác biệt về mức độ ảnh hưởng.

### Hiệu suất và nỗ lực

Có thể theo dõi số bước, số lần quay lại, số lần tìm kiếm, số lần mở trợ giúp, số lần nhập lại dữ liệu và mức độ cần hỗ trợ. Chỉ số cần gắn với mục tiêu: ít bước hơn không có ý nghĩa nếu người dùng không hiểu hoặc thiếu bước xác nhận cần thiết.

### Sự hài lòng và mức độ tự tin

Sau tác vụ, hỏi người tham gia đánh giá mức độ dễ thực hiện, sự rõ ràng và mức tự tin rằng họ đã đạt kết quả. Dùng cùng câu hỏi và thang đo trong các phiên để so sánh. Lời nhận xét định tính giúp giải thích điểm số, nhưng không nên biến một câu nói nổi bật thành kết luận cho toàn bộ nhóm.

### Khả năng học và ghi nhớ

Với sản phẩm được sử dụng không thường xuyên, khả năng nhớ cách làm sau một khoảng thời gian có thể quan trọng. Có thể cho người tham gia thực hiện tác vụ lần đầu, sau đó quay lại sau một khoảng thời gian phù hợp và quan sát họ có cần học lại nhiều không. Cần tính đến hiệu ứng nhớ từ lần thử trước và không coi kết quả của một phiên ngắn là đại diện cho khả năng ghi nhớ dài hạn.

| Chỉ số | Cách đo | Câu hỏi cần trả lời |
|---|---|---|
| Hoàn thành đúng | Số người hoàn thành theo tiêu chí / tổng số người thực hiện | Người dùng có đạt mục tiêu không? |
| Hoàn thành không trợ giúp | Số người hoàn thành mà không cần gợi ý | Giao diện có tự giải thích đủ không? |
| Thời gian tác vụ | Thời gian từ mốc bắt đầu đến hoàn thành | Tác vụ mất bao lâu trong điều kiện đã định? |
| Lỗi nghiêm trọng | Số lỗi gây hậu quả lớn hoặc làm sai kết quả | Rủi ro nào cần ưu tiên sửa? |
| Số lần trợ giúp | Lượt yêu cầu trợ giúp hoặc gợi ý của điều phối viên | Người dùng bị mắc kẹt ở đâu? |
| Điểm dễ sử dụng | Thang đo chuẩn hoặc câu hỏi nhất quán | Người tham gia cảm nhận thế nào? |
| Khả năng ghi nhớ | Mức hỗ trợ và hiệu suất ở lần quay lại | Người dùng có nhớ cách thực hiện không? |

## 7. Chuẩn bị và điều hành một phiên đánh giá

Một phiên tốt cần kịch bản nhất quán, môi trường sẵn sàng và người điều phối được chuẩn bị. Nên chạy thử (pilot) với một người hoặc đồng nghiệp không tham gia thiết kế để phát hiện tác vụ mơ hồ, lỗi tài khoản và vấn đề ghi nhận trước khi mời người tham gia chính thức.

### Trước phiên

- Xác nhận người tham gia phù hợp tiêu chí tuyển chọn và đã đồng ý tham gia.
- Chuẩn bị kịch bản, tác vụ, câu hỏi sau tác vụ và tiêu chí hoàn thành.
- Kiểm tra thiết bị, trình duyệt, kết nối, tài khoản, quyền và dữ liệu.
- Đảm bảo dữ liệu ban đầu đúng và có thể khôi phục cho phiên tiếp theo.
- Kiểm tra công cụ ghi chú, ghi âm, ghi hình hoặc chia sẻ màn hình nếu có sự đồng ý.
- Phân công người điều phối, người ghi chép và người quan sát nếu cần.
- Chuẩn bị phương án khi hệ thống hoặc mạng gặp lỗi ngoài phạm vi đánh giá.

### Mở đầu phiên

Giải thích mục đích, thời lượng, cách sử dụng dữ liệu, việc ghi âm/ghi hình và quyền dừng bất cứ lúc nào. Nói rõ người tham gia đang giúp nhóm đánh giá sản phẩm; không có câu trả lời đúng hay sai về năng lực cá nhân. Khuyến khích họ mô tả điều họ đang nghĩ nếu phương pháp think-aloud được sử dụng.

Không tiết lộ trước nơi có nút hoặc cách hoàn thành tác vụ. Nếu người tham gia hỏi “Tôi có làm đúng không?”, có thể trả lời trung lập: “Bạn hãy làm theo cách bạn thấy hợp lý; chúng tôi muốn hiểu điều gì đang rõ hoặc chưa rõ trong sản phẩm.”

### Trong khi thực hiện

Quan sát trước khi can thiệp. Ghi lại hành động, lời nói, thời điểm do dự, thao tác quay lại, lỗi, kỳ vọng và phản ứng khi hệ thống trả kết quả. Khi cần hỏi thêm, dùng câu hỏi mở và không dẫn dắt.

Ví dụ câu hỏi trung lập:

- “Bạn đang tìm điều gì ở bước này?”
- “Bạn mong đợi điều gì sẽ xảy ra sau thao tác vừa rồi?”
- “Điều gì khiến bạn chọn cách đó?”
- “Bạn dựa vào đâu để biết tác vụ đã hoàn tất?”
- “Có thông tin nào bạn muốn thấy thêm không?”

Tránh giải thích giao diện ngay khi người tham gia gặp khó khăn, trừ khi mục tiêu của phiên đã kết thúc hoặc cần hỗ trợ để bảo đảm an toàn. Nếu phải gợi ý, hãy ghi nhận mức hỗ trợ vì nó ảnh hưởng đến cách tính hoàn thành độc lập.

### Kết thúc phiên

Hỏi người tham gia về điểm dễ, khó, điều gây bất ngờ và mức tự tin. Cảm ơn họ, nhắc lại cách dữ liệu được xử lý và giải quyết thù lao hoặc hỗ trợ đã thống nhất. Không hứa rằng mọi đề xuất sẽ được triển khai; giải thích rằng nhóm sẽ tổng hợp và đánh giá các phát hiện.

## 8. Ghi nhận và phân tích bằng chứng

Ghi nhận tốt giúp nhóm phân biệt điều thực sự quan sát được với cách diễn giải. Một bản ghi sự kiện nên có thời điểm, tác vụ, hành động, kết quả, lời nói liên quan và mức trợ giúp. Tránh ghi nhận xét mang tính phán xét như “người dùng không biết dùng máy tính”; thay vào đó ghi hành vi cụ thể như “đọc nhãn ba lần, chọn mục cài đặt, quay lại trang trước và hỏi liệu thay đổi đã được lưu chưa”.

### Mẫu ghi nhận một phát hiện

| Trường | Nội dung ví dụ |
|---|---|
| Mã phát hiện | U-07 |
| Nhóm người dùng | Khách hàng mới |
| Tác vụ | Gửi yêu cầu hoàn tiền |
| Quan sát | Người tham gia hoàn tất biểu mẫu nhưng không nhận ra nút xác nhận cuối trang |
| Bằng chứng | Cuộn lên xuống hai lần, dừng 18 giây và hỏi liệu đã gửi chưa |
| Hậu quả | Tác vụ không hoàn thành; có nguy cơ gửi lại hoặc liên hệ hỗ trợ |
| Nguyên nhân giả thuyết | Nút xác nhận thiếu nổi bật và trạng thái chưa rõ |
| Mức độ | Cao nếu tác vụ bị bỏ dở hoặc gửi trùng gây hậu quả nghiệp vụ |
| Đề xuất | Cải thiện vị trí, nhãn và phản hồi sau khi gửi; kiểm tra lại với người dùng |

Nguyên nhân trong ví dụ là giả thuyết, cần được xác minh. Người tham gia có thể bỏ lỡ nút vì độ tương phản, cách cuộn, nội dung hoặc sự gián đoạn. Không nên khẳng định nguyên nhân chỉ từ một hành vi đơn lẻ.

### Nhóm phát hiện theo mẫu

Sau các phiên, nhóm tổng hợp vấn đề theo tác vụ, nhóm người dùng, bước trong hành trình và loại rào cản. Nhiều người có thể gặp cùng vấn đề với biểu hiện khác nhau. Ngược lại, một vấn đề chỉ xảy ra với một nhóm nhỏ nhưng có thể là rào cản nghiêm trọng về khả năng tiếp cận.

Các nhóm thường gặp:

- Khó tìm chức năng hoặc không nhận biết bước tiếp theo.
- Nhãn, thông điệp hoặc thuật ngữ khó hiểu.
- Phản hồi hệ thống không rõ hoặc đến quá muộn.
- Người dùng không biết trạng thái đã lưu, gửi hoặc hoàn tất chưa.
- Lỗi nhập liệu và thiếu hướng dẫn sửa.
- Điều hướng, thứ tự tiêu điểm hoặc thao tác bàn phím không phù hợp.
- Nội dung không tương thích với công nghệ trợ giúp.
- Quy trình có quá nhiều bước hoặc yêu cầu thông tin không cần thiết.
- Trạng thái lỗi khiến người dùng mất dữ liệu hoặc không thể phục hồi.

### Ưu tiên phát hiện

Đánh giá mức độ theo tác động đến mục tiêu, tần suất quan sát, số nhóm bị ảnh hưởng, khả năng phục hồi và hậu quả nghiệp vụ. Có thể dùng thang nghiêm trọng từ thấp đến cao, nhưng cần mô tả tiêu chí để người đánh giá nhất quán.

Ví dụ, vấn đề căn lề nhỏ có thể có mức thấp; nhãn không rõ khiến người dùng chọn sai loại giao dịch có thể ở mức cao; rào cản khiến người dùng không thể hoàn thành thao tác thiết yếu bằng bàn phím có thể là nghiêm trọng dù chỉ ảnh hưởng một nhóm người dùng.

Không nên xếp hạng chỉ dựa trên số người gặp vấn đề. Hãy xem cả mức độ hậu quả và nghĩa vụ tiếp cận. Một vấn đề hiếm nhưng làm mất dữ liệu hoặc ngăn người dùng tiếp cận dịch vụ thiết yếu vẫn cần ưu tiên cao.

## 9. Kết hợp đánh giá khả năng sử dụng với kiểm thử chức năng và phi chức năng

Đánh giá khả năng sử dụng không thay thế kiểm thử chức năng. Hai hoạt động xác nhận các khía cạnh khác nhau và cần liên kết với nhau để tránh hiểu sai kết quả.

| Hoạt động | Câu hỏi chính | Ví dụ bằng chứng |
|---|---|---|
| Kiểm thử chức năng | Hệ thống có thực hiện đúng quy tắc và kết quả không? | Đơn hàng được tạo đúng, số tiền và trạng thái chính xác |
| Đánh giá khả năng sử dụng | Người dùng có thể tìm, hiểu và hoàn thành tác vụ không? | Tỷ lệ hoàn thành, thời gian, lỗi và hành vi do dự |
| Kiểm thử khả năng tiếp cận | Người dùng với các khả năng và công nghệ trợ giúp khác nhau có thể truy cập không? | Điều hướng bàn phím, nhãn đọc màn hình, tương phản và cấu trúc |
| Kiểm thử hiệu năng | Phản hồi có đủ nhanh trong điều kiện tải không? | Độ trễ, thời gian tải và lỗi theo tải |
| Kiểm thử độ tin cậy | Hệ thống có duy trì trạng thái và phục hồi đúng khi lỗi không? | Dữ liệu không mất, thông báo rõ và khả năng tiếp tục |

Ví dụ, một biểu mẫu có thể vượt qua kiểm thử chức năng vì dữ liệu được lưu đúng. Tuy nhiên, người dùng có thể không nhận ra trường bắt buộc, nhập sai định dạng và không hiểu thông báo lỗi. Đánh giá khả năng sử dụng phát hiện vấn đề về nội dung và quy trình; kiểm thử chức năng xác nhận bản sửa vẫn lưu đúng dữ liệu.

### Chuyển phát hiện thành trường hợp kiểm thử hồi quy

Khi phát hiện vấn đề, hãy xác định phần nào có thể chuyển thành kiểm thử tự động:

- Nhãn, nội dung, trạng thái và phản hồi có thể được kiểm tra bằng test giao diện hoặc component.
- Thứ tự tab, tên accessible và một số quy tắc cấu trúc có thể kiểm tra bằng công cụ tự động.
- Luồng nghiệp vụ có thể được xác nhận bằng E2E sau khi thiết kế được sửa.
- Hiệu năng tải trang hoặc phản hồi có thể được theo dõi bằng kiểm thử hiệu năng.
- Mức độ dễ hiểu, khả năng tìm thấy và cảm nhận vẫn cần đánh giá với người dùng hoặc chuyên gia phù hợp.

Không phải mọi phát hiện khả năng sử dụng đều có thể chuyển thành assertion tự động. Kiểm thử tự động giúp bảo vệ những thuộc tính có thể mô tả rõ; đánh giá với người dùng vẫn cần thiết để kiểm chứng trải nghiệm tổng thể.

## 10. Đánh giá khả năng tiếp cận cùng người dùng đại diện

Khả năng tiếp cận (accessibility) là điều kiện để người dùng có thể nhận biết, hiểu, điều hướng và tương tác với sản phẩm, kể cả khi họ có nhu cầu hoặc cách sử dụng khác nhau. Nó không chỉ là một tiêu chí bổ sung sau khi hoàn thành giao diện; nên được xem xét ngay khi xác định nhóm người dùng và thiết kế tác vụ.

### Chọn người tham gia theo nhu cầu tiếp cận

Khi mục tiêu liên quan đến công nghệ trợ giúp, hãy mời người dùng thực sự sử dụng các công nghệ đó, chẳng hạn trình đọc màn hình, phóng đại, điều khiển bằng bàn phím, nhập liệu bằng giọng nói hoặc thiết bị hỗ trợ vận động. Không nên giả định rằng người không có nhu cầu đó có thể mô phỏng chính xác trải nghiệm của họ bằng cách bịt mắt hoặc tắt màn hình.

Tôn trọng cách người tham gia muốn giao tiếp, thiết bị cá nhân và thời gian cần thiết. Chuẩn bị tài liệu ở định dạng tiếp cận được, cho phép nghỉ và không gây áp lực về tốc độ nếu tốc độ không phải mục tiêu đánh giá.

### Kiểm tra cả công cụ và trải nghiệm thực

Có thể kết hợp:

- Kiểm tra tự động về một số lỗi cấu trúc, thuộc tính và tương phản.
- Kiểm tra thủ công bằng bàn phím, thứ tự tiêu điểm và thông báo trạng thái.
- Kiểm tra bằng trình đọc màn hình và công nghệ trợ giúp được hỗ trợ.
- Đánh giá với người dùng có nhu cầu tiếp cận trong tác vụ thực tế.

Một trang có thể không có lỗi mà công cụ tự động phát hiện nhưng vẫn khó sử dụng vì thứ tự đọc không hợp lý, nhãn khó hiểu hoặc thông báo động không được công bố. Ngược lại, kết quả từ một phiên người dùng không thay thế việc kiểm tra có hệ thống theo tiêu chuẩn tiếp cận phù hợp.

## 11. Kiểm soát sai lệch và chất lượng nghiên cứu

Kết quả đánh giá có thể bị ảnh hưởng bởi cách tuyển người, cách viết tác vụ, thái độ điều phối viên, thiết bị và thứ tự thực hiện. Nhóm cần nhận diện các nguồn sai lệch để không diễn giải quá mức bằng chứng.

### Tránh câu hỏi dẫn dắt

Không hỏi “Bạn có thấy nút lưu màu xanh dễ nhìn không?” vì câu hỏi gợi ý rằng nút đó dễ nhìn và hướng người tham gia đến một yếu tố cụ thể. Hãy hỏi “Bạn sẽ làm gì tiếp theo?” hoặc “Bạn mong đợi điều gì xảy ra?”.

### Không hướng dẫn quá sớm

Nếu người điều phối giải thích cách dùng khi người tham gia do dự, nhóm sẽ mất cơ hội quan sát vấn đề. Hãy để họ thử theo cách tự nhiên trong giới hạn thời gian đã định. Nếu cần can thiệp, ghi lại thời điểm, nội dung gợi ý và tác động đến kết quả.

### Giữ điều kiện nhất quán

Sử dụng cùng kịch bản, tiêu chí hoàn thành và cách ghi nhận cho những người tham gia trong cùng một nghiên cứu. Nếu có thay đổi giữa các phiên, ghi rõ để tránh so sánh trực tiếp những dữ liệu không tương đương.

### Tránh thiên lệch tuyển mẫu

Không chỉ tuyển đồng nghiệp, người quen hoặc người dùng thành thạo vì họ dễ tiếp cận. Nhóm này có thể hiểu thuật ngữ nội bộ và bỏ qua vấn đề của người mới. Hãy so sánh mẫu thực tế với tiêu chí tuyển chọn và ghi nhận nhóm nào chưa được đại diện.

### Phân biệt quan sát và suy luận

Ghi rõ đâu là hành động được nhìn thấy, đâu là lời người tham gia nói và đâu là giả thuyết của nhóm. Một người dừng lại 10 giây là quan sát; kết luận họ “không hiểu” là diễn giải cần được xác minh bằng câu hỏi hoặc bằng chứng khác.

## 12. Đạo đức, quyền riêng tư và sự đồng thuận

Người tham gia cần biết mục đích buổi đánh giá, dữ liệu nào được thu thập, ai có thể truy cập, dữ liệu được lưu bao lâu và họ có thể rút lui như thế nào. Sự đồng thuận cần tự nguyện và được ghi nhận trước khi bắt đầu ghi âm, ghi hình hoặc thu thập dữ liệu cá nhân.

Một số nguyên tắc thực hành:

- Chỉ thu thập dữ liệu cần thiết để trả lời câu hỏi đánh giá.
- Dùng tài khoản và dữ liệu tổng hợp; tránh hiển thị thông tin khách hàng thật.
- Ẩn danh hoặc giả danh dữ liệu khi chia sẻ kết quả rộng hơn nhóm nghiên cứu.
- Giới hạn quyền truy cập bản ghi, ảnh chụp và thông tin liên hệ.
- Xác định thời hạn lưu và cách xóa dữ liệu sau nghiên cứu.
- Không ghi nhận mật khẩu, token hoặc dữ liệu thanh toán thật.
- Cho phép người tham gia nghỉ hoặc dừng mà không bị gây áp lực.
- Có phương án hỗ trợ khi tác vụ chạm đến nội dung nhạy cảm hoặc gây khó chịu.

Nếu ghi hình màn hình, cần kiểm tra nội dung có thể xuất hiện ngoài tác vụ, chẳng hạn thông báo cá nhân hoặc các tab khác. Chỉ ghi phần cần thiết và thông báo rõ trước phiên. Khi sử dụng dịch vụ nghiên cứu bên ngoài, xác minh cách họ xử lý dữ liệu và quyền truy cập.

## 13. Chuyển kết quả thành cải tiến có thể kiểm chứng

Đánh giá chỉ tạo ra giá trị khi phát hiện được chuyển thành quyết định và được kiểm tra lại. Một báo cáo dài với nhiều trích dẫn nhưng không có mức ưu tiên, người phụ trách hoặc hành động tiếp theo khó giúp sản phẩm tiến bộ.

### Viết phát hiện rõ ràng

Mỗi phát hiện nên mô tả:

- Nhóm người dùng và tác vụ bị ảnh hưởng.
- Hành vi quan sát được và bằng chứng cụ thể.
- Kết quả hoặc hậu quả đối với mục tiêu.
- Mức độ nghiêm trọng và mức độ chắc chắn.
- Nguyên nhân giả thuyết nếu có, được phân biệt với sự kiện đã xác nhận.
- Đề xuất cải tiến hoặc câu hỏi cần nghiên cứu thêm.
- Người sở hữu và cách xác nhận sau khi sửa.

### Ưu tiên và lập kế hoạch

Có thể dùng ma trận tác động và tần suất, nhưng cần xem xét hậu quả và nhóm người dùng. Một vấn đề làm người dùng không thể hoàn thành tác vụ quan trọng nên được ưu tiên cao dù chỉ quan sát ở một số ít người. Một vấn đề thẩm mỹ nhỏ có thể được đưa vào kế hoạch sau nếu không ảnh hưởng đến khả năng nhận biết hoặc thao tác.

Chuyển phát hiện thành công việc có tiêu chí hoàn thành rõ. Ví dụ, “cải thiện thông báo” quá mơ hồ; có thể cụ thể hóa thành “sau khi gửi yêu cầu hoàn tiền, giao diện hiển thị xác nhận, mã yêu cầu và trạng thái tiếp theo; người dùng thử nghiệm có thể nhận biết yêu cầu đã được tiếp nhận mà không cần trợ giúp”.

### Đánh giá lại sau cải tiến

Sau khi sửa, kiểm thử lại với người dùng đại diện phù hợp hoặc thực hiện phương pháp đánh giá tương đương. So sánh cùng tác vụ, điều kiện và tiêu chí; xem vấn đề cũ đã giảm chưa và có vấn đề mới phát sinh không. Không nên giả định một thay đổi giao diện chỉ cải thiện một khía cạnh; ví dụ, thêm bước xác nhận có thể giảm lỗi nhưng làm tăng thời gian và số thao tác.

## 14. Ví dụ thực hành: đánh giá luồng đặt lịch khám

Giả sử một ứng dụng cho phép người dùng tìm cơ sở y tế, chọn chuyên khoa, đặt lịch và nhận xác nhận. Nhóm muốn đánh giá xem người dùng mới có thể hoàn thành đặt lịch và hiểu chính xác trạng thái hay không.

### Xác định mục tiêu và người tham gia

Nhóm xác định các nhóm cần đại diện gồm người dùng mới, người thường xuyên đặt lịch cho bản thân hoặc người thân, và người dùng cần hỗ trợ tiếp cận nếu ứng dụng hướng đến nhóm này. Bối cảnh gồm điện thoại di động, kết nối mạng không ổn định và người dùng có thể không quen thuật ngữ y tế.

Mục tiêu đánh giá:

- Tìm đúng cơ sở và chuyên khoa theo nhu cầu.
- Chọn được khung giờ phù hợp và hoàn thành đặt lịch.
- Hiểu lịch đã được tiếp nhận hay đã được cơ sở xác nhận.
- Biết cách xem, đổi hoặc hủy lịch theo chính sách.

### Thiết kế tác vụ

“Bạn cần đặt lịch khám chuyên khoa da liễu tại cơ sở gần nơi ở vào tuần tới. Hãy tìm một khung giờ phù hợp, hoàn tất quy trình và cho biết bạn dựa vào đâu để biết lịch đã được xác nhận.”

Tác vụ không chỉ kiểm tra việc nhấn nút đặt lịch mà còn xem người dùng hiểu sự khác biệt giữa yêu cầu đặt lịch và xác nhận từ cơ sở hay không.

### Bằng chứng cần thu thập

| Khía cạnh | Bằng chứng |
|---|---|
| Hiệu quả | Người dùng chọn đúng cơ sở, chuyên khoa và khung giờ; lịch được tạo đúng |
| Hiệu suất | Thời gian, số bước quay lại và số lần tìm kiếm |
| Lỗi | Chọn nhầm chuyên khoa, ngày hoặc cơ sở; gửi trùng yêu cầu |
| Sự rõ ràng | Người dùng giải thích đúng trạng thái tiếp nhận và xác nhận |
| Khả năng tiếp cận | Điều hướng bàn phím, tên trường, thứ tự đọc và thông báo trạng thái |
| Phục hồi | Người dùng xử lý được khi khung giờ vừa hết hoặc mạng bị ngắt |

### Phân tích và cải tiến

Giả sử nhiều người chọn được giờ nhưng nghĩ lịch đã xác nhận ngay khi thấy thông báo “Đặt lịch thành công”. Trong thực tế, cơ sở y tế cần xác nhận sau đó. Đây là vấn đề ngữ nghĩa và kỳ vọng, không phải lỗi tạo dữ liệu. Nhóm có thể đổi thông báo thành “Yêu cầu đặt lịch đã được gửi; cơ sở sẽ xác nhận trong thời gian dự kiến”, hiển thị trạng thái chờ và hướng dẫn cách theo dõi.

Sau khi sửa, nhóm kiểm tra lại với người dùng đại diện và xác nhận họ phân biệt được trạng thái yêu cầu với lịch đã xác nhận. Đồng thời, kiểm thử chức năng xác nhận trạng thái trong hệ thống được cập nhật đúng và E2E bảo vệ luồng thông báo. Như vậy, đánh giá khả năng sử dụng được kết nối với kiểm thử chức năng và vận hành.

## 15. Những sai lầm thường gặp

- **Tuyển người thuận tiện thay vì người phù hợp:** đồng nghiệp hoặc người dùng thành thạo có thể không đại diện cho nhóm mục tiêu.
- **Dùng tác vụ dẫn dắt:** chỉ đường đến nút làm mất cơ hội phát hiện vấn đề tìm kiếm và hiểu giao diện.
- **Hỏi người dùng họ thích gì thay vì quan sát:** sở thích tự báo cáo không luôn phản ánh khả năng hoàn thành tác vụ.
- **Chỉ đo thời gian:** người dùng có thể làm nhanh nhưng sai hoặc bỏ qua bước quan trọng.
- **Coi một buổi thử là đại diện cho toàn bộ quần thể:** kết quả cần được diễn giải theo phương pháp lấy mẫu và phạm vi người tham gia.
- **Dùng một cỡ mẫu cố định cho mọi nghiên cứu:** nghiên cứu định tính khám phá và nghiên cứu định lượng cần cách chọn mẫu khác nhau.
- **Điều phối viên giúp quá sớm:** gợi ý làm sai lệch mức độ hoàn thành độc lập.
- **Chỉ đánh giá trên thiết bị của nhóm phát triển:** môi trường không phản ánh điều kiện người dùng thực.
- **Bỏ qua người dùng có nhu cầu tiếp cận:** có thể tạo rào cản với tác vụ thiết yếu.
- **Nhầm quan sát với nguyên nhân:** hành vi do dự không tự chứng minh nguyên nhân là nhãn hoặc bố cục.
- **Không bảo vệ dữ liệu người tham gia:** bản ghi và ảnh chụp có thể chứa thông tin cá nhân hoặc bí mật.
- **Không kiểm thử lại sau sửa:** nhóm không biết cải tiến có giải quyết vấn đề hoặc tạo vấn đề mới không.
- **Coi đánh giá khả năng sử dụng là hoạt động cuối dự án:** vấn đề phát hiện muộn có thể tốn kém và khó sửa hơn.

## 16. Danh sách kiểm tra cho một nghiên cứu khả năng sử dụng

**Mục tiêu và phạm vi**

- Nhóm người dùng, bối cảnh và tác vụ đã được xác định chưa?
- Mục tiêu đánh giá có thể quan sát hoặc đo lường được không?
- Tác vụ có phản ánh luồng quan trọng và ngoại lệ có rủi ro không?

**Người tham gia**

- Tiêu chí tuyển chọn có gắn với người dùng thực tế không?
- Có bao gồm khác biệt về kinh nghiệm, vai trò, thiết bị và nhu cầu tiếp cận liên quan không?
- Cỡ mẫu có phù hợp với mục tiêu định tính hay định lượng không?
- Người tham gia đã được thông báo và đồng thuận chưa?

**Kịch bản và môi trường**

- Tác vụ có trung lập, không tiết lộ đường đi hoặc câu trả lời không?
- Trạng thái ban đầu, dữ liệu và quyền đã được chuẩn bị chưa?
- Thiết bị, trình duyệt, mạng và công cụ ghi nhận đã được kiểm tra chưa?
- Đã chạy thử kịch bản và xác nhận thời lượng chưa?

**Thu thập và phân tích**

- Có ghi nhận hoàn thành, thời gian, lỗi, trợ giúp và phản hồi không?
- Quan sát, lời nói và giả thuyết có được phân biệt không?
- Phát hiện được ưu tiên theo hậu quả và nhóm bị ảnh hưởng không?
- Dữ liệu cá nhân và bản ghi được bảo vệ theo thỏa thuận không?

**Cải tiến và xác minh**

- Mỗi phát hiện quan trọng có người phụ trách và hành động cụ thể không?
- Có tiêu chí xác nhận sau khi sửa không?
- Các kiểm thử chức năng, khả năng tiếp cận hoặc E2E liên quan đã được cập nhật chưa?
- Nhóm đã đánh giá lại với người dùng phù hợp sau cải tiến chưa?

## Kết luận

Kết hợp đánh giá khả năng sử dụng với người dùng đại diện giúp kiểm chứng liệu sản phẩm có thực sự hỗ trợ những người mà nó phục vụ trong bối cảnh sử dụng của họ hay không. Một nghiên cứu có giá trị cần xác định rõ nhóm người dùng và tác vụ, tuyển người phù hợp, dùng kịch bản trung lập, quan sát hành vi và đo hiệu quả, hiệu suất cùng sự hài lòng. Khi phát hiện được phân tích có căn cứ, chuyển thành cải tiến và kiểm tra lại bằng người dùng cùng các kiểm thử chức năng, khả năng tiếp cận và E2E, nhóm có thể cải thiện trải nghiệm mà vẫn giữ tính đúng đắn và độ tin cậy của hệ thống.
