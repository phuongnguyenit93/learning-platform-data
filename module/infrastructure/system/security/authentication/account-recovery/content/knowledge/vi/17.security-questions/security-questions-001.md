# Điểm yếu của câu hỏi bảo mật trong khôi phục tài khoản

## Mục tiêu và phạm vi

Trong chương **Security Questions** của module **SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY**, bài học này giải thích vì sao câu hỏi bảo mật có thể làm suy yếu cơ chế khôi phục tài khoản. Bối cảnh gồm người dùng quên mật khẩu, mất phương thức MFA, mất passkey hoặc mất thiết bị xác thực.

Một hệ thống có thể dùng passkey để chống giả mạo trang đăng nhập nhưng vẫn cho phép thay passkey sau khi trả lời tên thú cưng. Khi đó, người tấn công không cần phá cơ chế mật mã của passkey; họ tìm cách được hệ thống cấp quyền đăng ký phương thức xác thực mới qua nhánh khôi phục.

Sau bài học, người học cần có khả năng:

- Phân biệt thông tin về một người với bằng chứng người đang yêu cầu thực sự kiểm soát tài khoản.
- Giải thích các điểm yếu về khả năng đoán, tính công khai, tương quan, khả năng ghi nhớ và quyền riêng tư.
- Nhận diện đường vòng qua câu hỏi bảo mật trong luồng đặt lại mật khẩu, MFA và passkey.
- Đề xuất cách chuyển hệ thống cũ sang quy trình khôi phục có bằng chứng phù hợp, quyền hạn hẹp, token dùng một lần và kiểm soát session.

Các tình huống, số liệu xác suất và chính sách trong bài là ví dụ minh họa do bài học xây dựng, không phải kết quả đo lường trên một hệ thống thực tế.

## 1. Câu hỏi bảo mật thực sự chứng minh điều gì?

Câu hỏi bảo mật thường yêu cầu một dữ kiện mà người dùng được kỳ vọng nhớ được:

| Câu hỏi | Điều hệ thống muốn suy ra | Điều câu trả lời đúng thực sự cho biết |
| --- | --- | --- |
| Tên thú cưng đầu tiên của bạn là gì? | Đây là chủ tài khoản | Người yêu cầu biết một tên liên quan đến người dùng |
| Bạn học trường tiểu học nào? | Đây là người đã đăng ký | Người yêu cầu biết một phần tiểu sử |
| Bạn sinh ra ở thành phố nào? | Danh tính đã được xác minh | Người yêu cầu biết hoặc đoán đúng một địa danh |
| Món ăn yêu thích của bạn là gì? | Người yêu cầu có bí mật riêng | Người yêu cầu biết giá trị đã được lưu trước đây |

Điểm khác biệt nằm ở **quyền kiểm soát**. Chữ ký từ một khóa đã đăng ký chứng minh quyền kiểm soát khóa trong giao dịch đó. Câu trả lời về trường học không chứng minh quyền kiểm soát thiết bị, khóa, hộp thư hay mã khôi phục nào.

Cơ chế dựa trên hiểu biết về tiểu sử thường được gọi là **knowledge-based authentication**, viết tắt là KBA. Câu trả lời có thể bí mật ở thời điểm đăng ký, nhưng sự kiện trong đời người không được tạo ra để làm bí mật xác thực.

Cũng cần tách KBA khỏi thông tin phục vụ điều tra. Nhân viên hỗ trợ có thể cần mô tả sự cố để tìm hồ sơ, nhưng tìm đúng hồ sơ chưa đủ để cấp quyền thay phương thức xác thực.

### Định hướng từ tài liệu tham khảo

OWASP cảnh báo không dùng câu hỏi bảo mật trong thiết kế phần mềm an toàn mới; phần hướng dẫn chi tiết của tài liệu này dành cho hệ thống cũ. Vì vậy, tối ưu cách lưu câu trả lời chỉ là biện pháp chuyển tiếp. Xem [OWASP Choosing and Using Security Questions](https://cheatsheetseries.owasp.org/cheatsheets/Choosing_and_Using_Security_Questions_Cheat_Sheet.html).

NIST SP 800-63B-4, mục 3.1.1.2, cấm yêu cầu KBA hoặc câu hỏi bảo mật khi chọn mật khẩu. Mục 4.2 mô tả các cơ chế khôi phục như mã khôi phục, liên hệ khôi phục và xác minh lại danh tính. Đây là các yêu cầu có phạm vi cụ thể; không nên diễn giải một câu về mật khẩu thành mọi yêu cầu tuân thủ cho mọi loại hệ thống. Xem [NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html).

Với module này, định hướng thiết kế là: **câu trả lời về tiểu sử không đủ để cho phép đặt lại thông tin đăng nhập hoặc thay phương thức xác thực**.

## 2. Mô hình đe dọa: ai có thể biết câu trả lời?

Chỉ đánh giá người lạ không biết gì về nạn nhân sẽ bỏ sót nhiều tác nhân quan trọng.

| Tác nhân | Kiến thức hoặc khả năng có thể có | Vì sao câu hỏi bảo mật yếu trước tác nhân đó |
| --- | --- | --- |
| Người lạ thu thập hồ sơ công khai | Bài đăng, ảnh, hồ sơ nghề nghiệp, trang trường học | Câu trả lời có thể tìm được mà không cần truy cập tài khoản |
| Người quen, đồng nghiệp, người thân | Quê quán, trường học, sở thích, tên người thân | Có lợi thế lớn so với người đoán ngẫu nhiên |
| Người từng có quan hệ gần gũi | Lịch sử cá nhân, thông tin gia đình, cách viết quen dùng | Một bí mật đối với người lạ có thể hoàn toàn không bí mật với họ |
| Kẻ có dữ liệu rò rỉ từ dịch vụ khác | Câu trả lời hoặc thông tin hồ sơ từng được dùng lại | Bí mật có thể bị tái sử dụng giữa các hệ thống |
| Kẻ đánh cắp cơ sở dữ liệu | Hash câu trả lời, salt, mã câu hỏi | Có thể kiểm tra ứng viên ngoại tuyến |
| Người điều khiển nhiều nguồn gửi yêu cầu | Nhiều IP, trình duyệt hoặc tài khoản tự động | Có thể phân tán việc thử nếu chỉ giới hạn theo IP |
| Người lừa nhân viên hỗ trợ | Một phần tiểu sử và câu chuyện có vẻ hợp lý | Có thể biến cuộc gọi hỗ trợ thành nhánh khôi phục yếu hơn |

Tài sản cần bảo vệ không chỉ là mật khẩu hiện tại. Đó còn là quyền thay email khôi phục, vô hiệu MFA, thêm passkey, cấp lại recovery code và chấm dứt hoặc duy trì session.

Một câu trả lời đúng có thể dẫn tới hậu quả rất khác nhau tùy quyền được cấp sau đó. Vì vậy, cần xem cả câu hỏi lẫn hành động cuối cùng mà hệ thống cho phép.

## 3. Điểm yếu thứ nhất: dữ kiện cá nhân không phải bí mật bền vững

### 3.1. Thông tin có thể công khai hoặc suy ra

Một bức ảnh thú cưng có chú thích, bài viết về ngày đầu đi học hoặc hồ sơ giới thiệu quê quán đều có thể cung cấp dữ kiện để trả lời. Việc người dùng không chủ động công khai “câu trả lời bảo mật” không có nghĩa dữ kiện tương ứng chưa từng xuất hiện ở nơi khác.

Một câu hỏi còn có thể thu hẹp không gian tìm kiếm. Nếu hệ thống hiển thị “Bạn tốt nghiệp trường trung học nào?”, người tấn công biết cần tìm loại thông tin nào, thay vì phải đoán một chuỗi bí mật bất kỳ.

### 3.2. Người quen có thể trả lời tốt hơn người lạ

Câu hỏi về tên mẹ, ngày kỷ niệm hoặc địa chỉ cũ thường đặc biệt yếu trước người thân hay người từng sống cùng. Đây là lý do không thể dùng cảm giác “thông tin này khá riêng tư” để đánh giá khả năng chống chiếm đoạt tài khoản.

Thiết kế cần bảo vệ cả trường hợp người yêu cầu là người dùng thật lẫn trường hợp người yêu cầu biết rõ cuộc đời họ.

### 3.3. Dữ kiện khó thu hồi sau khi lộ

Mật khẩu có thể thay bằng một chuỗi mới. Khóa xác thực bị lộ có thể được thu hồi và thay khóa. Người dùng không thể thay quá khứ đã học ở đâu hoặc sinh ra ở thành phố nào.

Đổi sang câu hỏi khác cũng không bảo đảm giải quyết vấn đề nếu các câu hỏi mới tiếp tục dựa trên cùng hồ sơ đã bị lộ. Một sự cố dữ liệu có thể làm giảm giá trị của cả nhóm câu hỏi trong thời gian dài.

## 4. Điểm yếu thứ hai: khả năng đoán bị đánh giá quá cao

### 4.1. Nhiều đáp án có thể tồn tại nhưng không được chọn đều

Giả sử một câu hỏi có 100 đáp án hợp lý. Nếu mỗi đáp án có xác suất đúng bằng nhau, mức bất định lý tưởng là:

~~~text
log2(100) ≈ 6,64 bit
~~~

Đây chỉ là mô hình phân bố đều. Thực tế của từng hệ thống phải được đánh giá riêng. Chẳng hạn, trong một phân bố giả định, đáp án phổ biến nhất chiếm 30% thì chỉ một lần thử đáp án đó đã có xác suất thành công 30%.

Một đại lượng mô tả khả năng đoán tốt nhất trong một lần là min-entropy:

~~~text
H_min(A) = -log2(max_a P(A = a))

Nếu đáp án phổ biến nhất có xác suất 0,30:
H_min(A) ≈ 1,74 bit
~~~

Con số này không phải số lần thử trung bình cần để đoán hết mọi câu trả lời. Nó chỉ nhấn mạnh rằng đếm số đáp án khả dĩ không đủ để suy ra sức chống đoán.

### 4.2. Phải tính theo thông tin người tấn công đã biết

Gọi C là ngữ cảnh người tấn công có, chẳng hạn khu vực sinh sống, độ tuổi hoặc trường từng theo học. Nếu họ chọn g ứng viên có xác suất cao nhất theo C, xác suất đoán đúng là:

~~~text
P_thành_công(g | C)
    = tổng xác suất của g đáp án được chọn, với điều kiện C
~~~

Ví dụ giả định: năm đáp án đầu bao phủ 65% người dùng trong một nhóm cụ thể. Cho phép năm lần thử không tạo ra mức bảo vệ tương đương một bí mật ngẫu nhiên chỉ vì hệ thống có hàng trăm đáp án khác có thể nhập.

Khi tấn công nhắm vào một cá nhân, thông tin C có thể làm câu trả lời gần như chắc chắn. Khi tấn công diện rộng, việc thử ít ứng viên phổ biến trên nhiều tài khoản lại là rủi ro khác.

### 4.3. Độ dài không đồng nghĩa với độ khó đoán

“Tên đầy đủ của trường đại học” có thể dài hơn 30 ký tự nhưng vẫn là tên của một tổ chức công khai. Bắt câu trả lời có chữ hoa, số hoặc ký tự đặc biệt có thể khiến người dùng thêm một hậu tố quen thuộc mà không làm dữ kiện gốc trở thành bí mật tốt.

Nếu người dùng tự tạo chuỗi ngẫu nhiên để trả lời, độ khó đoán có thể tăng. Tuy nhiên, lúc đó hệ thống thực chất đang quản lý một mật khẩu phụ phải được cất giữ. Nó chưa có vòng đời dùng một lần của recovery code và không giải quyết được nhu cầu “khôi phục vì không còn nhớ hoặc giữ được bí mật”.

## 5. Điểm yếu thứ ba: nhiều câu hỏi không tự tạo thành MFA

MFA đòi hỏi các loại yếu tố xác thực khác nhau. Mật khẩu và câu trả lời bảo mật đều thuộc nhóm kiến thức; dùng cả hai không tự biến giao dịch thành xác thực đa yếu tố.

Tương tự, ba câu hỏi không phải ba yếu tố độc lập. Chúng có thể cùng bị suy ra từ một hồ sơ:

- Quê quán và trường tiểu học có quan hệ địa lý.
- Tên thú cưng và tên gọi thân mật có thể cùng xuất hiện trong một nhóm bài đăng.
- Tên cha mẹ và tên thời con gái của mẹ có thể cùng nằm trong dữ liệu gia đình.

Với hai câu trả lời A và B, cùng ngữ cảnh C:

~~~text
P(đúng A và đúng B | C)
    = P(đúng A | C) × P(đúng B | đúng A, C)
~~~

Chỉ khi có giả định độc lập phù hợp mới được thay vế thứ hai bằng P(đúng B | C). Không được tùy ý nhân hai tỷ lệ đoán riêng lẻ rồi tuyên bố hệ thống đã mạnh hơn tương ứng.

Cách tổ chức câu hỏi cũng ảnh hưởng kết quả:

| Quy tắc | Hệ quả cần phân tích |
| --- | --- |
| Đúng bất kỳ một trong ba câu | Người tấn công chọn câu dễ nhất |
| Đúng hai trong ba câu | Những cặp câu cùng nguồn dữ liệu có thể làm giảm giá trị bổ sung |
| Đúng cả ba câu | Có thể tăng số người dùng thật thất bại nhưng chưa loại bỏ tương quan |
| Cho người dùng đổi bộ câu hỏi mỗi lần thử | Có thể mở thêm cơ hội tìm câu dễ và né giới hạn theo challenge |
| Hiển thị câu nào đúng, câu nào sai | Tạo phản hồi để ghép dần một bộ câu trả lời |

Thêm một bước vào giao diện có thể làm luồng dài hơn mà không bổ sung bằng chứng độc lập tương xứng.

## 6. Điểm yếu thứ tư: băm câu trả lời không sửa được nguồn bí mật yếu

Cần phân biệt hai đường tấn công.

**Đoán trực tuyến:** người tấn công gửi câu trả lời tới dịch vụ. Biện pháp giới hạn tốc độ và số lần thử có tác dụng ở đây.

**Đoán ngoại tuyến:** người tấn công có dữ liệu kiểm tra câu trả lời, chẳng hạn hash sau một sự cố. Giới hạn tốc độ của API không còn kiểm soát việc thử trên bản dữ liệu đó.

Nếu hệ thống cũ vẫn lưu câu trả lời, cần bảo vệ chúng như bí mật: không lưu rõ, không ghi log và dùng cơ chế băm mật khẩu có salt riêng cùng chi phí phù hợp. OWASP cũng đề cập cách xử lý câu trả lời tương tự mật khẩu trong phần dành cho hệ thống cũ. Xem [OWASP về lưu câu trả lời](https://cheatsheetseries.owasp.org/cheatsheets/Choosing_and_Using_Security_Questions_Cheat_Sheet.html#storing-answers).

Tuy vậy:

- Salt riêng làm giảm khả năng tái sử dụng tính toán giữa nhiều bản ghi; salt không biến tên một trường học thành chuỗi ngẫu nhiên.
- Hàm băm tốn chi phí làm mỗi lần thử đắt hơn; nó không làm tăng số ứng viên thực sự cần thử.
- Mã hóa có thể bảo vệ một số tình huống mất bản sao dữ liệu, nhưng hệ thống có khóa giải mã vẫn có khả năng đọc câu trả lời.
- Không có cách lưu trữ nào ngăn người quen nhập ngay câu trả lời chính xác vào giao diện.

Đánh giá “đã hash nên an toàn” chỉ nhìn vào một lớp bảo vệ. Quyền được cấp sau khi câu trả lời khớp mới quyết định câu trả lời đó có thể trở thành đường chiếm đoạt tài khoản hay không.

## 7. Điểm yếu thứ năm: khó vừa dễ nhớ vừa khó đoán

Khôi phục thường diễn ra sau một thời gian dài và trong trạng thái căng thẳng. Người dùng có thể nhớ dữ kiện nhưng không nhớ cách đã nhập:

| Vấn đề | Ví dụ | Rủi ro thiết kế |
| --- | --- | --- |
| Dấu và cách viết | “Hòa” so với “Hoa” | Người dùng thật có thể bị từ chối nếu khác quy ước |
| Biệt danh và tên chính thức | Tên gọi ở nhà so với tên trên hồ sơ | Một câu hỏi có nhiều câu trả lời hợp lý |
| Cách ghi địa danh | Tên cũ, tên mới, tên viết tắt | Dữ kiện nhớ được nhưng biểu diễn đã thay đổi |
| Thay đổi sở thích | Món ăn hoặc đội thể thao yêu thích | Câu trả lời hiện tại khác câu trả lời khi đăng ký |
| Câu hỏi không phù hợp | Không có thú cưng hoặc không biết thông tin gia đình | Người dùng bịa đáp án dễ quên hoặc phải bỏ cuộc |

Chuẩn hóa đầu vào có thể giảm một số lỗi, nhưng cũng có thể làm nhiều giá trị khác nhau bị coi là một:

- Chuẩn hóa Unicode NFC xử lý một số biểu diễn tương đương; việc này khác với bỏ dấu.
- Chuyển chữ thường và bỏ khoảng trắng đầu cuối cần có quy tắc thống nhất khi lưu và khi kiểm tra.
- Bỏ dấu có thể làm “Hoa” và “Hòa” trùng nhau.
- So khớp gần đúng mở rộng tập câu trả lời được chấp nhận và có thể làm việc đoán dễ hơn.

Đối với dữ liệu cũ, quy tắc chuẩn hóa còn cần được quản lý theo phiên bản. Đổi quy tắc kiểm tra trong khi không thể tạo lại hash gốc có thể làm câu trả lời hợp lệ trước đây không còn dùng được.

Điều đáng chú ý là mâu thuẫn trong chính thiết kế: đáp án tự nhiên dễ nhớ thường dễ liên hệ với người dùng; đáp án ngẫu nhiên khó đoán lại cần được lưu như một bí mật riêng. Câu hỏi bảo mật không tự giải quyết được mâu thuẫn đó.

## 8. Điểm yếu thứ sáu: rò rỉ qua giao diện, API và hỗ trợ

### 8.1. Lộ sự tồn tại của tài khoản

Nếu nhập email hợp lệ sẽ thấy bộ câu hỏi, còn email không tồn tại nhận lỗi khác, dịch vụ đã cung cấp tín hiệu để dò tài khoản. Khác biệt có thể nằm ở nội dung, mã HTTP, bước chuyển trang hoặc thời gian xử lý.

Thiết kế phản hồi cần xét toàn bộ hành trình trước xác minh. Chỉ dùng một thông báo chung trong khi API vẫn trả cấu trúc dữ liệu khác nhau là chưa đủ. Thêm thời gian chờ ngẫu nhiên cũng không thay thế được việc loại bỏ khác biệt có thể quan sát.

### 8.2. Phản hồi từng phần hỗ trợ đoán

Thông báo “Câu 1 đúng, câu 2 sai” biến dịch vụ thành một công cụ xác nhận từng phần. Tương tự, gợi ý độ dài, ký tự đầu hoặc hiển thị lại một phần câu trả lời có thể tiết lộ thông tin.

Với nhánh cũ chưa thể loại bỏ ngay, giao diện không nên trả lại câu trả lời đã lưu, kể cả cho nhân viên hỗ trợ. Cơ chế xác minh cũng không nên cung cấp phản hồi giúp ghép từng đáp án đúng.

### 8.3. Giới hạn theo IP hoặc session có thể không đủ

Giới hạn chỉ theo IP không xử lý tốt nguồn gửi phân tán. Giới hạn chỉ theo recovery session có thể bị vô hiệu nếu người tấn công tạo session mới.

Một thiết kế chống lạm dụng cần phối hợp ngân sách thử theo tài khoản hoặc định danh chuẩn hóa ở phía máy chủ, theo hồ sơ khôi phục, theo nguồn gửi và theo toàn dịch vụ. Việc tạo challenge mới không được tự động làm mới ngân sách thử của cùng tài khoản.

Ngược lại, khóa toàn bộ tài khoản chỉ vì nhiều yêu cầu khôi phục chưa được xác minh có thể giúp người tấn công gây từ chối dịch vụ. Có thể chặn hoặc trì hoãn nhánh khôi phục mà vẫn cho phép người dùng đăng nhập bằng phương thức hợp lệ đang có.

Các biện pháp này giới hạn lạm dụng; chúng không làm câu trả lời cá nhân trở thành bằng chứng mạnh.

### 8.4. Hỗ trợ thủ công có thể mở lại đường đã đóng

Nếu giao diện tự phục vụ không còn dùng câu hỏi nhưng tổng đài vẫn cho đổi số điện thoại sau khi đọc đúng địa chỉ cũ, rủi ro vẫn tồn tại.

Kịch bản hỗ trợ phải phân biệt rõ thông tin dùng để tìm hồ sơ, thông tin dùng để điều tra và bằng chứng đủ để phê duyệt thay đổi. Tình huống khẩn cấp hoặc câu chuyện thuyết phục không được tự động nâng một dữ kiện tiểu sử thành quyền thay MFA.

## 9. Điểm yếu thứ bảy: thu thập thêm dữ liệu nhạy cảm

Tên người thân, địa chỉ cũ, trường học và lịch sử cá nhân có thể ảnh hưởng cả người dùng lẫn người không có tài khoản trong hệ thống.

Một biểu mẫu câu hỏi bảo mật có thể:

- Thu thập dữ liệu không cần thiết cho chức năng chính.
- Làm lộ mối quan hệ gia đình hoặc thông tin gây khó chịu cho người dùng.
- Tạo dữ liệu có thể hỗ trợ tấn công khôi phục ở dịch vụ khác.
- Xuất hiện trong log, hệ thống phân tích hành vi, bản ghi cuộc gọi hoặc ticket hỗ trợ.

Bởi vậy, thay thế câu hỏi bảo mật cũng là cơ hội giảm dữ liệu cần bảo vệ. Không nên đổi từ hỏi tiểu sử sang yêu cầu nhiều ảnh giấy tờ tùy ý. Quy trình xác minh lại danh tính cần có mục đích, căn cứ liên kết với tài khoản, kiểm soát truy cập và thời hạn lưu giữ phù hợp.

Việc người yêu cầu có một giấy tờ mang tên nào đó chưa tự chứng minh họ sở hữu một tài khoản ẩn danh chưa từng được gắn đáng tin cậy với danh tính đó.

## 10. Đường vòng nguy hiểm trong khôi phục mật khẩu, MFA và passkey

Xét thiết kế giả định sau:

~~~mermaid
flowchart TD
    A["Nhập định danh tài khoản"] --> B["Trả lời câu hỏi bảo mật"]
    B --> C{"Câu trả lời khớp?"}
    C -- "Không" --> D["Từ chối hoặc cho thử lại"]
    C -- "Có" --> E["Cấp quyền thay thông tin đăng nhập"]
    E --> F["Đặt mật khẩu hoặc thêm phương thức xác thực mới"]
    F --> G["Đăng nhập bằng phương thức vừa được cấp"]
~~~

Lỗi nằm ở cạnh chuyển từ “biết câu trả lời” sang “được thay thông tin đăng nhập”. Người tấn công chỉ cần vượt qua cơ chế khôi phục này nếu nó có đủ quyền thay thế cơ chế đăng nhập bình thường.

Những biểu hiện cụ thể gồm:

| Hành động sau câu trả lời đúng | Rủi ro |
| --- | --- |
| Cho đặt lại mật khẩu | Lấy được quyền kiểm soát yếu tố mật khẩu |
| Cho đổi email khôi phục | Chuyển các lần xác minh tiếp theo sang địa chỉ của người tấn công |
| Cho tắt MFA | Bỏ yêu cầu sở hữu yếu tố bổ sung |
| Cho thêm passkey | Đăng ký khóa do người tấn công kiểm soát |
| Cấp session đầy đủ | Truy cập dữ liệu trước khi hoàn tất kiểm tra cần thiết |
| Cho cấp lại recovery code | Tạo bí mật mới để duy trì khả năng quay lại |

Mất passkey trên thiết bị không có nghĩa hệ thống có thể tái tạo khóa riêng từ câu trả lời bảo mật. Điều mà nhánh khôi phục thường làm là cho phép gắn phương thức mới. Chính quyền gắn mới đó cần được bảo vệ.

Tương tự, khôi phục quyền đăng nhập không tự bảo đảm khôi phục được dữ liệu mã hóa đầu cuối. Nếu không còn khóa giải mã hoặc cơ chế dự phòng tương ứng, câu hỏi bảo mật không thể tạo lại khóa mật mã đã mất.

OWASP nêu rõ câu hỏi bảo mật không được làm cơ chế duy nhất để đặt lại mật khẩu vì đáp án thường dễ đoán hoặc tìm được. Đây là giới hạn quan trọng, không phải bảo đảm rằng cứ thêm câu hỏi vào một luồng bất kỳ là luồng đó đạt mức bảo đảm mong muốn. Xem [OWASP Forgot Password](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#security-questions).

## 11. Thiết kế thay thế: tách bằng chứng, đánh giá rủi ro và quyền khôi phục

### 11.1. Chọn phương án theo những gì người dùng còn kiểm soát

| Tình trạng | Hướng thiết kế cần xem xét | Giới hạn phải giữ |
| --- | --- | --- |
| Còn phương thức xác thực khác đã đăng ký | Xác thực lại bằng phương thức đó trước khi gắn phương thức mới | Session cũ hoặc cookie đơn thuần chưa chắc đủ cho thao tác nhạy cảm |
| Còn mã khôi phục đã cấp trước | Kiểm tra mã theo chính sách, tiêu thụ dùng một lần | Mã phải được gắn với tài khoản và mục đích; không coi một mã là đủ cho mọi mức bảo đảm |
| Còn kênh khôi phục đã xác minh | Gửi thử thách tới kênh đã đăng ký từ trước | Không gửi bí mật phê duyệt tới địa chỉ mới chỉ do người yêu cầu khai |
| Mất MFA nhưng còn mật khẩu | Kết hợp bằng chứng bổ sung theo chính sách thay MFA | Mật khẩu cộng câu hỏi bảo mật không tạo thành MFA |
| Mất mọi phương thức | Quy trình hỗ trợ hoặc xác minh lại đã được thiết kế trước | Không chuyển sang hỏi tiểu sử vì thuận tiện |
| Không đủ bằng chứng liên kết với tài khoản | Giữ yêu cầu chưa được phê duyệt và cung cấp hướng xử lý phù hợp | Không có nghĩa hệ thống luôn có thể khôi phục an toàn |

Kênh email hay SMS có mô hình rủi ro riêng, như bị chiếm hộp thư hoặc mất quyền kiểm soát số điện thoại. Chúng không tự tương đương passkey hay tự đáp ứng mọi yêu cầu khôi phục MFA. Phải đánh giá cả cách kênh được thiết lập, khả năng người yêu cầu kiểm soát kênh và mức bảo đảm mà tài khoản cần.

### 11.2. Tín hiệu rủi ro không phải bằng chứng sở hữu

Thiết bị quen, địa chỉ mạng quen hoặc lịch sử sử dụng có thể giúp quyết định cần kiểm tra thêm, tạm giữ hay chuyển hỗ trợ. Chúng không nên tự động bù cho việc thiếu bằng chứng bắt buộc.

Với hệ thống đang chuyển đổi, câu trả lời bảo mật nếu còn xuất hiện trong hồ sơ điều tra cũng không được tăng quyền khôi phục, giảm yêu cầu bằng chứng hoặc trở thành điều kiện bắt buộc khiến người dùng thật không thể đi tiếp. Việc trả lời sai một câu hỏi vốn dễ nhầm không tự chứng minh có gian lận.

Một chính sách rõ ràng nên phân biệt:

- **Bằng chứng:** đã được máy chủ xác minh và liên kết với tài khoản, yêu cầu cùng mục đích cụ thể.
- **Tín hiệu rủi ro:** thông tin để tăng kiểm soát hoặc chuyển xem xét.
- **Quyết định cấp quyền:** kết quả áp dụng chính sách cho thao tác khôi phục cụ thể.

### 11.3. Minh họa ranh giới trong logic máy chủ

Đoạn sau là mã giả theo cú pháp Java, không phải triển khai hoàn chỉnh. Các đối tượng bằng chứng và kết quả chính sách phải do dịch vụ tin cậy tạo; chúng không phải các cờ boolean lấy trực tiếp từ request của trình duyệt.

~~~java
// Thiết kế yếu: dữ kiện tiểu sử quyết định quyền thay MFA.
if (answersMatch(request.answers())) {
    disableMfa(account);
    issueFullSession(account);
}
~~~

Một ranh giới phù hợp hơn:

~~~java
RecoveryDecision evaluate(
        RecoveryCase recoveryCase,
        VerifiedEvidence evidence,
        RiskAssessment risk) {

    // Chỉ dùng bằng chứng đã được xác minh ở phía máy chủ.
    var admissible = evidence.excludingSecurityQuestions();

    if (!admissible.isBoundTo(
            recoveryCase.accountId(),
            recoveryCase.id(),
            recoveryCase.purpose())) {
        return RecoveryDecision.requireMoreEvidence();
    }

    // Chính sách phụ thuộc hành động: đặt mật khẩu khác với thay MFA.
    if (!policy.meetsRequiredEvidence(recoveryCase, admissible)) {
        return RecoveryDecision.requireMoreEvidence();
    }

    if (risk.requiresReview()) {
        return RecoveryDecision.pendingReview();
    }

    // Đây là quyết định, chưa phải session đăng nhập.
    return RecoveryDecision.allowScopedRecovery();
}
~~~

Đoạn mã chỉ minh họa việc câu hỏi bảo mật không được tính vào bằng chứng đủ để cấp quyền. Các điều kiện về độ mới, hết hạn, tính độc lập của bằng chứng và trạng thái tài khoản vẫn cần được thực thi bởi các thành phần tương ứng.

Không nên thêm một nhánh kiểu “nếu không còn phương thức nào thì chấp nhận câu trả lời bảo mật” ở cuối hàm. Nhánh đó sẽ khôi phục lại chính đường vòng đang cần loại bỏ.

## 12. Token dùng một lần và session phải giữ ranh giới sau xác minh

Một quy trình không còn dùng câu hỏi bảo mật vẫn có thể sai nếu cấp quyền quá rộng sau bước xác minh. Với thiết kế minh họa của module, khi bằng chứng đạt yêu cầu, hệ thống chỉ cấp quyền cho hành động đã được phê duyệt.

Ví dụ: quyền đặt mật khẩu mới không mặc nhiên bao gồm quyền đổi email, tắt MFA hoặc thêm passkey.

Một recovery grant cần được kiểm tra ít nhất theo các thuộc tính sau:

| Thuộc tính | Mục đích |
| --- | --- |
| Tài khoản và hồ sơ khôi phục | Không dùng kết quả xác minh của tài khoản hoặc hồ sơ khác |
| Mục đích và hành động được phép | Không dùng quyền đặt mật khẩu để thay MFA |
| Thời điểm cấp và hết hạn | Giới hạn thời gian sử dụng quyền |
| Trạng thái chưa tiêu thụ | Không chấp nhận phát lại |
| Phiên bản chính sách hoặc trạng thái bảo mật liên quan | Vô hiệu quyền cũ khi điều kiện tài khoản đã thay đổi |

Nếu grant được biểu diễn bằng token bí mật ngẫu nhiên, token phải đủ khó đoán và được bảo vệ trong lưu trữ, truyền tải cũng như log. Việc tiêu thụ grant và cập nhật thông tin xác thực cần có cơ chế nguyên tử hoặc kiểm soát đồng thời tương đương; hai request song song không được cùng dùng một quyền.

Các nguyên tắc token ngẫu nhiên an toàn, hết hạn và dùng một lần cũng được OWASP liệt kê cho luồng đặt lại mật khẩu. Xem [OWASP Forgot Password: hướng dẫn chung](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html#general-security-practices).

Đối với khôi phục sau nghi ngờ bị chiếm đoạt, thiết kế cần xử lý cả session và các quyền còn tồn đọng:

- Thu hồi session, refresh token và các grant cũ thuộc phạm vi cần vô hiệu.
- Đánh giá và thu hồi phương thức xác thực bị mất hoặc bị nghi lộ; không xóa mọi phương thức một cách máy móc.
- Buộc đăng nhập theo chính sách sau khi thay đổi, thay vì tự cấp session đầy đủ từ nhánh câu hỏi cũ.
- Thông báo qua kênh đã đăng ký thích hợp, kèm cách báo cáo yêu cầu không được phép.
- Ghi lại sự kiện, phương thức xác minh và quyết định; không ghi câu trả lời, token hoặc mã khôi phục.

Với access token tự chứa, xóa session phía trình duyệt không tự làm token đã phát hành mất hiệu lực. Cần cơ chế thực thi việc thu hồi hoặc giới hạn thời gian hiệu lực phù hợp với kiến trúc và mức rủi ro của thao tác.

## 13. Ví dụ xuyên suốt: mất điện thoại có MFA

Lan đăng nhập bằng mật khẩu và ứng dụng tạo OTP trên điện thoại. Cô đã đăng một số ảnh thú cưng và thông tin trường học lên trang cá nhân.

Trong thiết kế cũ, người yêu cầu chỉ cần trả lời đúng hai câu hỏi để đổi mật khẩu và tắt MFA. Một người biết đủ tiểu sử của Lan có thể vượt qua nhánh này mà không giữ điện thoại hoặc recovery code.

Băm câu trả lời không ngăn tình huống đó: người yêu cầu đang nhập đúng dữ kiện vào giao diện hợp lệ.

Thiết kế thay thế xử lý theo bằng chứng còn lại:

1. Lan khai báo mất điện thoại để mở hồ sơ khôi phục; việc khai báo chưa làm thay đổi MFA hoặc khóa tài khoản.
2. Hệ thống yêu cầu tổ hợp bằng chứng đã được chính sách xác định cho việc thay MFA, chẳng hạn mã khôi phục hợp lệ cùng phương thức xác thực còn giữ.
3. Nếu không đạt yêu cầu, hồ sơ chuyển sang quy trình hỗ trợ đã được kiểm soát. Tiểu sử đúng không làm thay thế bằng chứng còn thiếu.
4. Khi được phê duyệt, quyền cấp ra chỉ phục vụ thay phương thức MFA trong hồ sơ đó.
5. Khi hoàn tất, hệ thống tiêu thụ quyền, xử lý phương thức cũ và session theo chính sách, rồi gửi thông báo phù hợp.

Nếu Lan chỉ còn biết tên thú cưng và trường học, hệ thống chưa đủ căn cứ để kết luận cô là chủ tài khoản. Cảm giác bất tiện ở đây phản ánh thiếu bằng chứng, không phải lý do để tạo một nhánh xác thực yếu hơn.

## 14. Chuyển đổi hệ thống cũ mà không mở thêm đường vòng

Việc ngừng dùng câu hỏi bảo mật cần xem cả sản phẩm, API và vận hành.

1. **Lập danh sách mọi nơi tiêu thụ kết quả trả lời.** Bao gồm web, ứng dụng di động, API cũ, công cụ quản trị, tổng đài và quy trình của đơn vị hỗ trợ.
2. **Ngừng đăng ký mới câu hỏi bảo mật.** Khi người dùng đang có phiên đủ tin cậy, hướng dẫn thiết lập phương án khôi phục thay thế. Việc thêm hoặc đổi phương án phải yêu cầu xác thực lại thích hợp.
3. **Chuẩn bị phương án cho người chỉ còn câu hỏi cũ.** Có quy trình hỗ trợ với tiêu chí bằng chứng rõ ràng; không yêu cầu họ dùng lại dữ kiện tiểu sử để hợp thức hóa phương án mới.
4. **Gỡ quyền cấp ra từ câu trả lời.** Việc này phải diễn ra ở phía máy chủ, bao gồm cả đường API cũ và quyền ngoại lệ của nhân viên hỗ trợ.
5. **Xử lý dữ liệu tồn đọng.** Xóa câu trả lời và dữ liệu liên quan theo chính sách lưu giữ, xử lý cả log và bản sao lưu trong vòng đời của chúng; không sao chép giá trị cũ sang trường ghi chú hỗ trợ.
6. **Theo dõi kết quả chuyển đổi.** Quan sát người dùng không thể hoàn tất, yêu cầu hỗ trợ, dấu hiệu lạm dụng và sự kiện chiếm đoạt. Tỷ lệ hoàn tất cao đơn thuần chưa chứng minh luồng an toàn.

Không nên tự động bỏ MFA hoặc đổi kênh khôi phục cho nhóm người dùng khó chuyển đổi. Những thay đổi đó cần được phê duyệt dựa trên bằng chứng phù hợp như các thao tác nhạy cảm khác.

## 15. Các tình huống cần dùng để kiểm chứng thiết kế

Bảng này mô tả kết quả mong muốn để người học đánh giá một thiết kế; không phải báo cáo hệ thống đã được triển khai hoặc kiểm thử.

| Tình huống | Kết quả mong muốn |
| --- | --- |
| Người yêu cầu biết toàn bộ câu trả lời nhưng không có bằng chứng được chấp nhận | Không được đặt lại mật khẩu, thay MFA, thêm passkey hoặc nhận session đầy đủ |
| Người quen biết nhiều tiểu sử của chủ tài khoản | Không được hưởng nhánh hỗ trợ có yêu cầu bằng chứng thấp hơn |
| Tạo nhiều hồ sơ để thử lại cùng tài khoản | Không làm mới toàn bộ ngân sách thử ở phía máy chủ |
| Gửi nhiều yêu cầu thất bại nhắm vào người khác | Không tự động khóa mọi cách đăng nhập hợp lệ của nạn nhân |
| Có grant cho đặt mật khẩu nhưng gửi request đổi MFA | Bị từ chối vì khác mục đích |
| Gửi đồng thời hai request dùng một grant | Chỉ một thao tác được tiêu thụ quyền thành công |
| Đọc bản ghi hỗ trợ hoặc log ứng dụng | Không thấy câu trả lời, token hoặc recovery code |
| Hoàn tất khôi phục sau sự cố chiếm đoạt | Session và quyền cũ thuộc phạm vi thu hồi không tiếp tục giúp người tấn công quay lại |
| Người dùng thật quên cách viết câu trả lời cũ nhưng có bằng chứng hợp lệ | Không bị chặn chỉ vì câu hỏi bảo mật |
| Tài khoản chưa từng gắn với danh tính ngoài đời | Không chấp nhận tùy ý giấy tờ mới như bằng chứng sở hữu tài khoản |

Điểm cần giữ khi đánh giá mọi biến thể là: biết thông tin về chủ tài khoản không đồng nghĩa kiểm soát tài khoản. Một luồng khôi phục an toàn phải kiểm tra bằng chứng phù hợp với hành động sắp cấp quyền, đồng thời kiểm soát lạm dụng, quyền khôi phục dùng một lần và session sau thay đổi.
