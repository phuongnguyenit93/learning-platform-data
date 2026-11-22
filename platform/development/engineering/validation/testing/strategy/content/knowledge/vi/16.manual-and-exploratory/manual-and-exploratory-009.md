# Cân đối kiểm thử có kịch bản với khám phá theo tình huống

Trong chiến lược kiểm thử xác thực (**VALIDATION_TESTING_STRATEGY**), kiểm thử có kịch bản và kiểm thử khám phá là hai cách tiếp cận bổ sung cho nhau. Kiểm thử có kịch bản (scripted testing) dùng các bước, dữ liệu và kết quả mong đợi đã được thiết kế trước để xác minh hành vi cụ thể một cách nhất quán. Kiểm thử khám phá (exploratory testing) kết hợp việc học về sản phẩm, thiết kế phép thử và thực hiện kiểm tra trong cùng một hoạt động, dựa trên quan sát và câu hỏi phát sinh khi tương tác với hệ thống.

Nếu chỉ dựa vào kịch bản có sẵn, nhóm có thể bỏ lỡ hành vi bất thường mà người viết test chưa dự đoán. Nếu chỉ khám phá tự do, kết quả có thể khó tái lập, khó đo mức bao phủ và khó dùng làm bằng chứng hồi quy. Cần cân đối hai cách tiếp cận theo mục tiêu, rủi ro, mức độ ổn định của tính năng, lịch sử lỗi và loại bằng chứng cần có.

Bài học này trình bày cách phân biệt hai cách tiếp cận, chọn tỷ trọng phù hợp, tổ chức phiên khám phá có mục tiêu, chuyển phát hiện thành kiểm thử có thể duy trì và đánh giá hiệu quả của cả hai.

## 1. Hiểu hai cách tiếp cận

### 1.1. Kiểm thử có kịch bản

Kiểm thử có kịch bản bắt đầu từ một trường hợp đã được thiết kế. Người thực hiện biết trước điều kiện, bước thao tác, dữ liệu đầu vào và kết quả mong đợi. Kịch bản có thể được thực hiện thủ công hoặc tự động.

Một kịch bản thường có:

- Mục tiêu hoặc yêu cầu cần xác minh.
- Điều kiện tiên quyết và trạng thái ban đầu.
- Dữ liệu đầu vào.
- Các bước thực hiện theo thứ tự.
- Kết quả mong đợi ở từng bước quan trọng.
- Kết quả thực tế và bằng chứng.
- Thông tin môi trường, phiên bản và cấu hình.

Ví dụ, kịch bản kiểm tra đăng nhập có thể yêu cầu mở trang đăng nhập, nhập tài khoản hợp lệ, gửi biểu mẫu và xác nhận người dùng được chuyển đến trang chính. Một kịch bản khác kiểm tra mật khẩu sai và xác nhận hệ thống từ chối đăng nhập, hiển thị thông báo phù hợp và không tạo phiên hợp lệ.

Ưu điểm chính của kiểm thử có kịch bản là tính lặp lại và khả năng truy vết. Khi yêu cầu ổn định, nhóm có thể chạy lại cùng các bước sau mỗi thay đổi và so sánh kết quả. Kịch bản cũng thuận tiện để giao việc, kiểm tra hồi quy và tạo bằng chứng cho các yêu cầu quan trọng.

Giới hạn xuất hiện khi kịch bản chỉ kiểm tra những điều đã được dự đoán. Nếu người viết không nghĩ đến một tổ hợp dữ liệu, một trạng thái bất thường hoặc một cách sử dụng khác, kịch bản có thể không phát hiện vấn đề. Kịch bản quá chi tiết cũng có thể tốn công bảo trì khi giao diện hoặc quy trình thay đổi.

### 1.2. Kiểm thử khám phá

Kiểm thử khám phá là cách tiếp cận trong đó người kiểm thử vừa tìm hiểu sản phẩm, vừa thiết kế và thực hiện các phép thử dựa trên thông tin vừa thu được. Người kiểm thử không chỉ làm theo một danh sách bước cố định; họ quan sát phản hồi, hình thành giả thuyết, thay đổi dữ liệu hoặc hành động và tiếp tục điều tra.

Một phiên khám phá có thể bắt đầu bằng một mục tiêu như:

- Tìm cách làm cho quy trình thanh toán tạo ra trạng thái không nhất quán.
- Khám phá cách hệ thống xử lý thay đổi quyền trong khi người dùng đang đăng nhập.
- Tìm các trường hợp khiến biểu mẫu lưu dữ liệu sai hoặc mất dữ liệu.
- Kiểm tra khả năng phục hồi khi kết nối bị gián đoạn giữa một thao tác.

Người kiểm thử có thể thay đổi thứ tự thao tác, dùng dữ liệu bất thường, chuyển giữa các vai trò, tải lại trang, gửi yêu cầu lặp hoặc quan sát log trong phạm vi được phép. Họ ghi lại điều đã thử, điều đã quan sát, câu hỏi mới và phát hiện đáng chú ý.

Khám phá không đồng nghĩa với thao tác ngẫu nhiên. Một phiên tốt có mục tiêu, phạm vi, thời lượng và cách ghi nhận rõ. Người kiểm thử sử dụng hiểu biết về sản phẩm, kinh nghiệm, rủi ro và các kỹ thuật khám phá để tìm ra hành vi chưa được mô tả trong kịch bản.

### 1.3. So sánh hai cách tiếp cận

| Khía cạnh | Kiểm thử có kịch bản | Kiểm thử khám phá |
|---|---|---|
| Thiết kế | Các bước và kết quả mong đợi được xác định trước. | Thiết kế và thực hiện phép thử diễn ra đồng thời. |
| Mục tiêu điển hình | Xác minh yêu cầu đã biết và duy trì hồi quy. | Tìm hiểu hành vi, phát hiện vấn đề chưa được dự đoán và kiểm tra giả thuyết. |
| Tính lặp lại | Cao nếu dữ liệu và môi trường được kiểm soát. | Có thể tái lập nếu ghi lại thao tác, dữ liệu và điều kiện; thường ít cố định hơn. |
| Tính linh hoạt | Thấp hơn khi gặp hành vi ngoài kịch bản. | Cao; có thể đổi hướng theo quan sát. |
| Bằng chứng | Kết quả từng bước, pass/fail và liên kết yêu cầu. | Ghi chú phiên, đường đi đã khám phá, bằng chứng và phát hiện. |
| Phù hợp | Hành vi ổn định, quan trọng, cần kiểm tra thường xuyên. | Tính năng mới, phức tạp, chưa rõ, có nhiều trạng thái hoặc lịch sử lỗi bất ngờ. |
| Rủi ro nếu dùng đơn độc | Bỏ lỡ trường hợp chưa được dự đoán. | Khó chứng minh bao phủ đầy đủ và khó lặp lại nếu ghi chép kém. |

Không cần chọn một cách duy nhất cho toàn bộ sản phẩm. Câu hỏi đúng là phần nào cần tính lặp lại, phần nào cần khả năng thích ứng và cách kết hợp nào tạo ra bằng chứng đủ tin cậy.

## 2. Khi nào ưu tiên kiểm thử có kịch bản?

Kiểm thử có kịch bản nên là nền tảng cho các hành vi đã hiểu rõ, có tính ổn định và cần xác minh lặp lại.

### 2.1. Yêu cầu quan trọng và tiêu chí chấp nhận rõ

Nếu yêu cầu có kết quả mong đợi cụ thể, hãy tạo kịch bản để xác nhận nó. Ví dụ:

- Người dùng có vai trò phù hợp được phép tạo đơn hàng.
- Người dùng không có quyền bị từ chối khi truy cập tài nguyên.
- Tổng tiền được tính theo quy tắc thuế và giảm giá.
- Hệ thống từ chối dữ liệu vượt giới hạn.
- Trạng thái đơn chuyển đúng sau khi thanh toán thành công.

Các kịch bản này cần được liên kết với yêu cầu và chạy lại khi hành vi liên quan thay đổi.

### 2.2. Luồng nghiệp vụ cốt lõi cần hồi quy

Những luồng có tần suất sử dụng cao hoặc hậu quả lớn nên có kịch bản ổn định để chạy thường xuyên, chẳng hạn đăng nhập, đặt hàng, thanh toán, đổi mật khẩu hoặc khôi phục dữ liệu.

Kịch bản hồi quy cần tập trung vào kết quả có ý nghĩa và ranh giới chính. Không nên biến mỗi thao tác nhỏ thành một kịch bản dài nếu có thể kiểm tra độc lập ở tầng thấp hơn.

### 2.3. Kiểm tra cần bằng chứng nhất quán

Một số hoạt động cần kết quả có thể so sánh giữa các phiên bản hoặc giữa các môi trường. Kịch bản phù hợp khi cần:

- Xác nhận điều kiện phát hành đã định.
- Kiểm tra một ma trận trình duyệt hoặc cấu hình đã cam kết.
- Chứng minh một lỗi đã sửa không tái diễn.
- Lưu bằng chứng cho kiểm toán hoặc quy trình phê duyệt.
- Bàn giao cho nhiều người thực hiện với cùng cách hiểu.

Khi cần bằng chứng có thể kiểm tra lại, hãy ghi rõ phiên bản, dữ liệu, môi trường và tiêu chí đạt.

### 2.4. Kiểm tra lặp lại trong CI hoặc theo lịch

Các phép kiểm tra nhanh và ổn định có thể tự động hóa để chạy khi có thay đổi hoặc theo lịch. Kịch bản thủ công cũng có thể được duy trì cho hoạt động không phù hợp để tự động hóa, miễn là các bước và kết quả đủ rõ.

Không nên tự động hóa một kịch bản đang thay đổi liên tục hoặc chưa hiểu rõ hành vi. Trước tiên, hãy khám phá và ổn định cách xác minh; sau đó quyết định phần nào đáng tự động hóa.

## 3. Khi nào ưu tiên kiểm thử khám phá?

Kiểm thử khám phá đặc biệt hữu ích khi hiểu biết về sản phẩm chưa đầy đủ hoặc khi tổ hợp hành vi khó liệt kê trước.

### 3.1. Tính năng mới hoặc yêu cầu còn mơ hồ

Khi một tính năng mới được phát triển, có thể còn câu hỏi về trạng thái, quyền, dữ liệu biên và cách xử lý lỗi. Phiên khám phá giúp tìm hiểu sản phẩm thực sự hoạt động ra sao và phát hiện khoảng trống trong yêu cầu.

Ví dụ, yêu cầu “người dùng có thể chỉnh sửa hồ sơ” chưa nói rõ điều gì xảy ra khi người dùng đổi email, mất kết nối trong lúc lưu, mở hai tab hoặc phiên đăng nhập hết hạn. Khám phá có thể làm lộ các câu hỏi này trước khi nhóm đóng băng kịch bản.

### 3.2. Hệ thống phức tạp với nhiều trạng thái và tương tác

Khám phá hữu ích khi hành vi phụ thuộc vào:

- Nhiều vai trò và quyền.
- Trạng thái trước đó hoặc lịch sử giao dịch.
- Các thao tác đồng thời hoặc gửi lặp.
- Dịch vụ bên ngoài và xử lý bất đồng bộ.
- Mạng không ổn định, timeout hoặc retry.
- Feature flag và cấu hình khác nhau.
- Dữ liệu lớn, thiếu, trùng hoặc không nhất quán.

Không phải mọi tổ hợp đều có thể được liệt kê trước. Người kiểm thử có thể dùng một trạng thái quan sát được để đặt câu hỏi mới và điều chỉnh đường kiểm tra.

### 3.3. Sau khi có thay đổi lớn hoặc lỗi bất ngờ

Khi kiến trúc, luồng dữ liệu hoặc giao diện thay đổi đáng kể, các kịch bản cũ có thể chưa bao phủ hành vi mới. Khám phá giúp kiểm tra những tương tác ngoài dự kiến và xác định kịch bản nào cần cập nhật.

Sau một lỗi production hoặc lỗi nghiêm trọng, hãy khám phá các điều kiện lân cận: dữ liệu tương tự, vai trò khác, thao tác lặp, trạng thái trước/sau và điều kiện lỗi. Mục tiêu là hiểu phạm vi nguyên nhân và tìm thêm đường dẫn có thể tái diễn.

### 3.4. Khi cần học nhanh trước khi thiết kế test

Khám phá có thể được dùng ở giai đoạn refinement hoặc đầu một vòng phát triển để tìm hiểu hệ thống, xác nhận giả định và đề xuất kịch bản. Kết quả của phiên giúp nhóm biết cần kiểm tra gì, ở tầng nào và dữ liệu nào cần chuẩn bị.

## 4. Cân đối theo rủi ro, độ ổn định và mục tiêu

Không có tỷ lệ cố định như 70% scripted và 30% exploratory phù hợp cho mọi dự án. Tỷ trọng nên thay đổi theo độ trưởng thành của tính năng, mức độ hiểu biết, hậu quả nếu lỗi và nhu cầu hồi quy.

### 4.1. Các yếu tố quyết định

| Yếu tố | Nghiêng về kịch bản khi... | Nghiêng về khám phá khi... |
|---|---|---|
| Độ rõ yêu cầu | Quy tắc và kết quả đã rõ. | Yêu cầu còn mơ hồ hoặc có giả định chưa xác nhận. |
| Độ ổn định | Hành vi ít thay đổi. | Tính năng mới hoặc đang thay đổi nhanh. |
| Rủi ro | Cần xác minh lặp lại các kiểm soát quan trọng. | Cần tìm cách sử dụng sai hoặc tình huống chưa dự đoán. |
| Lịch sử lỗi | Có lỗi đã sửa cần hồi quy. | Lỗi khó tái lập hoặc có nhiều đường dẫn liên quan. |
| Mức độ phức tạp | Luồng có thể mô tả rõ bằng các bước. | Nhiều trạng thái, tương tác và phụ thuộc khó liệt kê. |
| Bằng chứng | Cần kết quả nhất quán, truy vết được. | Cần hiểu biết mới và phát hiện chưa biết. |
| Thời gian | Cần kiểm tra nhanh cùng một bộ điều kiện. | Cần tập trung điều tra một vùng chưa rõ. |

### 4.2. Ma trận định hướng

| Bối cảnh | Cách tiếp cận nên ưu tiên | Cách bổ sung |
|---|---|---|
| Quy tắc ổn định, đã hiểu rõ | Kịch bản | Phiên khám phá định kỳ khi có thay đổi đáng kể. |
| Tính năng mới, yêu cầu còn mở | Khám phá | Chuyển phát hiện quan trọng thành kịch bản. |
| Luồng thanh toán hoặc quyền truy cập trọng yếu | Kịch bản hồi quy có kiểm soát | Khám phá các điều kiện lạm dụng và lỗi bất thường. |
| Giao diện thay đổi liên tục | Khám phá để tìm hiểu | Giữ kịch bản cho hành trình và kết quả cốt lõi. |
| Lỗi production khó tái lập | Khám phá có mục tiêu | Tạo regression test sau khi tái hiện được lỗi. |
| Bản phát hành cần bằng chứng lặp lại | Kịch bản theo tiêu chí phát hành | Khám phá có timebox cho vùng rủi ro hoặc thay đổi mới. |

### 4.3. Tăng khám phá khi độ không chắc chắn cao

Nếu nhóm chưa hiểu rõ cách tính năng hoạt động, viết nhiều kịch bản sớm có thể tạo ra giả định sai. Hãy dành thời gian khám phá để hiểu các trạng thái và phản hồi thực tế, sau đó ổn định các kịch bản quan trọng.

Khi hành vi đã rõ, tăng tỷ trọng kịch bản hồi quy để bảo vệ những gì đã học được. Khám phá vẫn cần tiếp tục khi sản phẩm thay đổi, xuất hiện lỗi mới hoặc có tín hiệu từ vận hành.

### 4.4. Không giảm khám phá chỉ vì đã có nhiều test tự động

Một bộ test tự động lớn có thể kiểm tra rất tốt các hành vi đã được mã hóa nhưng vẫn bỏ qua những giả định sai trong chính bộ test. Khám phá giúp đặt câu hỏi ngoài các assertion hiện có và tìm ra vùng chưa được mô hình hóa.

Ngược lại, không nên dùng khám phá để thay thế các kịch bản quan trọng đã ổn định. Những lỗi từng xảy ra và các điều kiện phát hành cần được chuyển thành kiểm tra có thể lặp lại.

## 5. Tổ chức phiên kiểm thử khám phá có mục tiêu

Một phiên khám phá nên có cấu trúc đủ để giữ trọng tâm và tạo ra kết quả có thể bàn giao.

### 5.1. Viết charter cho phiên khám phá

Charter là mô tả ngắn về vùng cần khám phá, mục tiêu và giới hạn. Một charter tốt không liệt kê từng bước cố định; nó định hướng câu hỏi mà người kiểm thử cần tìm lời giải.

Ví dụ:

**Charter:** Khám phá hành vi cập nhật địa chỉ giao hàng khi đơn hàng ở các trạng thái khác nhau, tập trung vào quyền sở hữu, thay đổi đồng thời và phản hồi khi mạng bị gián đoạn.

Có thể bổ sung:

- Phạm vi: trang chi tiết đơn hàng, update API và service lưu địa chỉ.
- Vai trò: chủ đơn hàng và người dùng khác.
- Dữ liệu: đơn mới tạo, đã xác nhận và đã gửi.
- Giới hạn: chỉ dùng staging và tài khoản thử nghiệm.
- Câu hỏi: trạng thái nào được phép sửa, request lặp được xử lý ra sao và dữ liệu có nhất quán sau lỗi mạng không?

### 5.2. Timebox phiên làm việc

Timebox giúp phiên khám phá tập trung và dễ lập kế hoạch. Có thể chọn 30, 60 hoặc 90 phút tùy độ phức tạp. Thời lượng không phải thước đo chất lượng; điều quan trọng là có mục tiêu rõ và debrief sau phiên.

Một phiên có thể gồm:

1. Đọc charter và xác nhận môi trường.
2. Chuẩn bị dữ liệu, vai trò và công cụ quan sát.
3. Khám phá theo câu hỏi hoặc giả thuyết.
4. Ghi lại đường đi, kết quả và phát hiện.
5. Dành thời gian tái hiện các hành vi bất thường.
6. Debrief và quyết định bước tiếp theo.

Nếu xuất hiện một vấn đề nghiêm trọng, có thể dừng charter để thu thập bằng chứng và báo cáo theo quy trình sự cố.

### 5.3. Dùng câu hỏi và heuristic để mở rộng khám phá

Một số câu hỏi hữu ích:

- Điều gì xảy ra nếu thực hiện thao tác hai lần?
- Điều gì xảy ra nếu dữ liệu thiếu, rất lớn, trùng hoặc ở trạng thái cũ?
- Điều gì xảy ra nếu người dùng đổi vai trò hoặc phiên hết hạn giữa chừng?
- Điều gì xảy ra nếu mạng chậm, mất kết nối hoặc phản hồi đến sai thứ tự?
- Có thể quay lại, tải lại hoặc mở cùng tài nguyên ở nhiều tab không?
- Hệ thống hiển thị gì khi một bước thành công nhưng bước tiếp theo thất bại?
- Dữ liệu có bị lộ khi truy cập trực tiếp API hoặc thay đổi định danh không?
- Điều gì xảy ra khi chuyển giữa các trạng thái hoặc feature flag?

Heuristic là gợi ý để đặt câu hỏi, không phải danh sách bắt buộc. Hãy chọn câu hỏi phù hợp với chức năng và rủi ro.

### 5.4. Ghi chép trong khi khám phá

Ghi lại thông tin đủ để người khác hiểu và tái hiện:

- Charter và thời gian phiên.
- Người thực hiện và môi trường.
- Phiên bản, cấu hình và dữ liệu.
- Các đường đi hoặc biến thể đã thử.
- Quan sát và kết quả bất ngờ.
- Ảnh chụp, log, trace hoặc request/response đã lọc dữ liệu nhạy cảm.
- Câu hỏi chưa trả lời và vùng chưa được khám phá.
- Phát hiện, mức độ nghiêm trọng và bước tiếp theo.

Không cần ghi từng cú nhấp chuột nếu không có giá trị. Hãy ghi những bước quyết định và điều kiện cần để tái hiện hành vi.

## 6. Chuyển phát hiện khám phá thành kiểm thử có thể duy trì

Khám phá tạo ra hiểu biết mới. Nếu phát hiện quan trọng không được chuyển thành hành động, nhóm có thể phải tìm lại cùng lỗi ở lần sau.

### 6.1. Phân loại kết quả sau phiên

Một phiên có thể tạo ra:

- Lỗi đã xác nhận.
- Hành vi đúng nhưng chưa được tài liệu hóa.
- Yêu cầu hoặc tiêu chí chấp nhận còn mơ hồ.
- Rủi ro hoặc phụ thuộc chưa được kiểm tra.
- Ý tưởng cải tiến trải nghiệm hoặc khả năng quan sát.
- Kịch bản kiểm thử mới.
- Khu vực đã khám phá nhưng chưa thấy vấn đề trong điều kiện đã dùng.

Không tìm thấy lỗi không có nghĩa khu vực đã được chứng minh hoàn toàn an toàn. Hãy ghi điều kiện và giới hạn của phiên.

### 6.2. Tái hiện và xác nhận lỗi

Trước khi tạo bug, hãy cố gắng tái hiện với dữ liệu và điều kiện được kiểm soát. Ghi các bước tối thiểu, kết quả thực tế, kết quả mong đợi và bằng chứng. Nếu lỗi chỉ xảy ra không ổn định, ghi tần suất, điều kiện quan sát và các yếu tố có thể liên quan.

Không thay đổi dữ liệu production hoặc thử các thao tác có tác động ngoài phạm vi được phép để tái hiện lỗi. Dùng môi trường và tài khoản kiểm thử đã được phê duyệt.

### 6.3. Chuyển lỗi quan trọng thành regression test

Khi lỗi đã được sửa, tạo kiểm thử hồi quy ở tầng phù hợp:

- Unit test cho quy tắc hoặc nhánh logic gây lỗi.
- Integration test cho giao tiếp, transaction hoặc persistence.
- API test cho hợp đồng, quyền hoặc phản hồi.
- UI/E2E test cho hành trình người dùng nếu lỗi nằm ở tương tác xuyên suốt.

Không phải mọi lỗi khám phá đều cần một E2E test. Hãy đặt kiểm tra ở tầng có thể tái hiện nguyên nhân với chi phí và độ ổn định phù hợp. Có thể giữ một ca E2E đại diện nếu cần bảo vệ luồng quan trọng.

### 6.4. Cập nhật tài liệu và mô hình rủi ro

Nếu khám phá cho thấy yêu cầu chưa rõ, hãy chuyển câu hỏi cho chủ sở hữu sản phẩm. Nếu phát hiện một ranh giới hoặc tài sản chưa được xem xét, cập nhật phạm vi và danh mục rủi ro. Nếu test hiện tại bỏ sót hành vi, cập nhật ma trận bao phủ.

Mục tiêu là biến phát hiện thành cải tiến có người phụ trách, không chỉ lưu lại ghi chú trong báo cáo phiên.

## 7. Ví dụ: cân đối kiểm thử cho luồng thanh toán

Giả sử một tính năng thanh toán mới cho phép người dùng áp dụng mã giảm giá, chọn phương thức thanh toán và nhận callback từ nhà cung cấp.

### 7.1. Những gì nên kiểm tra bằng kịch bản

Các hành vi quan trọng và ổn định có thể được mô tả thành kịch bản:

- Người dùng thanh toán thành công và đơn chuyển sang PAID.
- Mã giảm giá hợp lệ được áp dụng đúng.
- Mã hết hạn bị từ chối.
- Người dùng không thể thanh toán đơn không thuộc quyền sở hữu.
- Callback hợp lệ cập nhật trạng thái giao dịch.
- Callback lặp không tạo giao dịch hoặc tác dụng phụ trùng.

Những kịch bản này nên được chạy lại khi thay đổi logic tính tiền, phân quyền, callback hoặc trạng thái đơn hàng.

### 7.2. Những gì nên khám phá

Trong giai đoạn đầu hoặc sau thay đổi lớn, tổ chức phiên khám phá với các câu hỏi:

- Điều gì xảy ra khi người dùng nhấn thanh toán nhiều lần?
- Điều gì xảy ra khi đóng tab ngay sau khi gửi request?
- Điều gì xảy ra khi callback đến trước khi trình duyệt nhận response?
- Điều gì xảy ra khi callback đến trễ hoặc theo thứ tự khác?
- Điều gì xảy ra khi mã giảm giá hết hạn trong lúc người dùng đang thanh toán?
- Điều gì xảy ra khi số tiền, đơn vị tiền tệ hoặc trạng thái trong request bị thay đổi?
- Điều gì xảy ra khi phiên đăng nhập hết hạn giữa quy trình?
- Giao diện có hiển thị đúng khi payment service timeout nhưng giao dịch đã được xử lý không?

Các câu hỏi này có thể làm lộ hành vi chưa được kịch bản ban đầu đề cập, chẳng hạn đơn bị tạo hai lần hoặc UI báo thất bại trong khi giao dịch đã thành công.

### 7.3. Chuyển kết quả thành bộ kiểm thử cân bằng

| Phát hiện hoặc mục tiêu | Cách tiếp cận duy trì |
|---|---|
| Quy tắc tính giảm giá và làm tròn | Unit test với phân vùng và giá trị biên. |
| Người dùng không thể thanh toán đơn của người khác | API regression test cho quyền sở hữu; E2E đại diện nếu cần kiểm tra trải nghiệm từ UI. |
| Nhấn nút thanh toán nhiều lần tạo request lặp | Kịch bản hồi quy cho idempotency và một phiên khám phá về thời điểm gửi lặp. |
| Callback đến trễ làm UI hiển thị sai | Integration test cho callback và một E2E test cho trạng thái chờ rồi cập nhật. |
| Phiên hết hạn giữa quy trình | API/UI test có kịch bản cho hành vi đã xác định; khám phá thêm các thời điểm chuyển tiếp. |
| Hành vi mới chưa được mô tả | Tiếp tục khám phá, làm rõ yêu cầu rồi tạo kịch bản phù hợp. |

Cách cân đối này tạo một bộ kịch bản ổn định cho hành vi cốt lõi và giữ thời gian khám phá để tìm rủi ro mới. Không cần biến mọi đường đi khám phá thành một kịch bản dài; chỉ giữ lại những hành vi quan trọng, có khả năng tái diễn hoặc cần bằng chứng lặp lại.

## 8. Kết hợp hai cách tiếp cận trong vòng đời phát triển

Có thể tổ chức theo chu trình sau:

1. **Trước phát triển:** dùng khám phá nguyên mẫu, phân tích yêu cầu và thử nghiệm kỹ thuật để tìm câu hỏi chưa rõ.
2. **Trong phát triển:** tạo kịch bản cho quy tắc đã thống nhất và các điều kiện chấp nhận.
3. **Khi tích hợp:** chạy kịch bản hồi quy và khám phá các ranh giới giữa thành phần.
4. **Trước phát hành:** chạy bộ kịch bản bắt buộc, sau đó dành timebox khám phá cho vùng rủi ro và thay đổi mới.
5. **Sau phát hành:** dùng dữ liệu vận hành và lỗi thực tế để định hướng phiên khám phá, rồi chuyển lỗi tái diễn thành regression test.

Chu trình này có thể lặp lại ở mỗi sprint hoặc mỗi bản phát hành. Tỷ trọng thay đổi theo mức độ hiểu biết: giai đoạn đầu thường cần khám phá nhiều hơn; khi hành vi ổn định, kịch bản hồi quy tăng lên; khi có thay đổi lớn, khám phá lại được tăng cường.

## 9. Đo lường hiệu quả mà không chạy theo số lượng

Không nên đánh giá chất lượng bằng số lượng kịch bản hoặc số giờ khám phá riêng lẻ. Hãy xem xét kết quả và giá trị của bằng chứng.

### 9.1. Chỉ số cho kiểm thử có kịch bản

- Tỷ lệ kịch bản quan trọng đã chạy trong mốc kiểm thử.
- Tỷ lệ pass/fail và xu hướng theo phiên bản.
- Số lỗi hồi quy được phát hiện.
- Thời gian chạy và chi phí bảo trì.
- Tỷ lệ kịch bản flaky hoặc thường xuyên cần bỏ qua.
- Mức truy vết từ yêu cầu đến ca kiểm thử và kết quả.

Một bộ kịch bản lớn nhưng không được cập nhật có thể tạo cảm giác an toàn giả. Cần xem xét test nào còn đại diện cho hành vi hiện tại.

### 9.2. Chỉ số cho kiểm thử khám phá

- Số charter hoàn thành và mục tiêu đã được khảo sát.
- Số phát hiện đã xác nhận, phân theo mức độ ảnh hưởng.
- Số câu hỏi hoặc giả định được làm rõ.
- Số lỗi khám phá được chuyển thành regression test.
- Thời gian từ phát hiện đến tái hiện và xử lý.
- Các vùng rủi ro đã khám phá và vùng còn bỏ ngỏ.

Không dùng số lượng bug làm mục tiêu duy nhất. Một phiên có ít lỗi nhưng làm rõ được một giả định quan trọng hoặc xác nhận một vùng rủi ro có thể tạo giá trị lớn.

### 9.3. Đánh giá kết hợp

Có thể theo dõi:

- Lỗi production có thể được phát hiện bằng kịch bản hiện có hay không.
- Lỗi mới có được chuyển thành kiểm thử hồi quy phù hợp không.
- Thời gian phát hiện lỗi trong thay đổi mới.
- Mức độ ổn định của bộ test.
- Những rủi ro chưa có bằng chứng.
- Tỷ lệ công việc phải làm lại do yêu cầu hoặc hành vi chưa được khám phá.

Dùng chỉ số để tìm điểm cải tiến, không dùng chúng để thúc đẩy người kiểm thử chạy theo số ca hoặc tạo phát hiện không có giá trị.

## 10. Vai trò và cách phối hợp

Kiểm thử có kịch bản và khám phá nên được thực hiện bởi nhóm có kỹ năng phù hợp và chia sẻ kết quả.

| Vai trò | Đóng góp |
|---|---|
| QA/test engineer | Thiết kế kịch bản, lập charter, thực hiện khám phá, ghi bằng chứng và đánh giá rủi ro. |
| Developer | Giải thích thiết kế, hỗ trợ tái hiện, viết regression test và xử lý nguyên nhân lỗi. |
| Product owner/analyst | Làm rõ hành vi mong đợi, quyết định nghiệp vụ và ưu tiên phát hiện. |
| Tech lead | Xác định ranh giới kỹ thuật, phụ thuộc và rủi ro kiến trúc. |
| Operations/SRE | Cung cấp thông tin vận hành, log, metric và điều kiện môi trường. |
| Cả nhóm | Tham gia debrief, cập nhật yêu cầu, phạm vi và tiêu chuẩn hoàn tất. |

Pair testing có thể hữu ích trong phiên khám phá: một người điều khiển và một người quan sát, đặt câu hỏi hoặc ghi chú. Hai người có thể luân phiên vai trò. Cách làm này giúp chia sẻ kiến thức và giảm việc bỏ qua giả định cá nhân.

## 11. Mẫu charter và báo cáo phiên khám phá

### 11.1. Mẫu charter

~~~text
Tên phiên:
Tính năng / phiên bản:
Mục tiêu khám phá:

Khám phá phần nào:
Câu hỏi hoặc giả thuyết:
Rủi ro cần tập trung:
Vai trò và dữ liệu:
Môi trường / cấu hình:
Giới hạn và điều kiện dừng:
Thời lượng:
Người tham gia:
~~~

### 11.2. Mẫu ghi nhận kết quả

~~~text
Tên phiên / charter:
Ngày và thời lượng:
Người thực hiện:
Phiên bản / môi trường / cấu hình:
Dữ liệu và tài khoản thử nghiệm:

Đường đi hoặc biến thể đã thử:
Quan sát:
Phát hiện đã xác nhận:
Bằng chứng (screenshot, log, trace, request/response):
Câu hỏi còn mở:
Vùng chưa được khám phá:
Rủi ro hoặc yêu cầu cần cập nhật:

Hành động tiếp theo:
- Bug cần tạo:
- Regression test cần bổ sung:
- Yêu cầu cần làm rõ:
- Rủi ro cần theo dõi:
Người phụ trách và thời hạn:
~~~

### 11.3. Mẫu ma trận cân đối

| Vùng chức năng | Kịch bản bắt buộc | Khám phá bổ sung | Lý do |
|---|---|---|---|
| Đăng nhập | Đăng nhập thành công, sai mật khẩu, session hết hạn. | Thử nhiều tab, thay đổi quyền và mạng gián đoạn. | Bảo vệ hành trình cốt lõi và tìm lỗi trạng thái phiên. |
| Thanh toán | Thành công, thất bại, callback hợp lệ và idempotency. | Callback trễ, request lặp, timeout và trạng thái không đồng bộ. | Hậu quả tài chính cao và có nhiều phụ thuộc. |
| Hồ sơ | Xem và cập nhật dữ liệu hợp lệ. | Unicode, dữ liệu dài, quyền chéo và lưu đồng thời. | Nhiều kiểu dữ liệu và ranh giới quyền. |
| Báo cáo | Bộ lọc và xuất dữ liệu theo tiêu chí. | Tổ hợp bộ lọc, dữ liệu rỗng và dữ liệu lớn. | Hành vi phụ thuộc dữ liệu và tải. |

Ma trận là công cụ lập kế hoạch. Hãy điều chỉnh theo sản phẩm, rủi ro và lịch sử lỗi; không cần áp dụng cùng một tỷ lệ cho mọi vùng.

## 12. Những sai lầm thường gặp

- **Coi khám phá là kiểm thử ngẫu nhiên:** phiên cần mục tiêu, phạm vi, thời lượng và ghi chép.
- **Chỉ dùng kịch bản có sẵn:** có thể bỏ lỡ hành vi ngoài dự đoán hoặc giả định sai trong test.
- **Chỉ khám phá mà không lưu kết quả:** khó tái lập, khó bàn giao và dễ lặp lại cùng hoạt động.
- **Viết kịch bản quá sớm khi yêu cầu chưa rõ:** dễ mã hóa giả định sai thành tiêu chí đạt.
- **Biến mọi thao tác khám phá thành test cố định:** bộ test phình to và khó bảo trì; chỉ giữ hành vi quan trọng.
- **Không tái hiện phát hiện trước khi báo lỗi:** thiếu điều kiện và bằng chứng có thể làm việc điều tra chậm.
- **Không chuyển lỗi đã sửa thành hồi quy:** lỗi có thể tái diễn mà không có kiểm tra bảo vệ.
- **Dùng số lượng bug để đánh giá phiên khám phá:** bỏ qua giá trị học hỏi và các giả định được làm rõ.
- **Không điều chỉnh theo rủi ro:** dành thời gian bằng nhau cho mọi chức năng dù hậu quả khác nhau.
- **Không debrief:** kết quả và câu hỏi chưa trả lời không được chuyển thành hành động.

## 13. Danh sách rà soát trước khi chốt kế hoạch

- [ ] Hành vi ổn định và quan trọng có kịch bản với kết quả mong đợi rõ ràng.
- [ ] Tính năng mới hoặc vùng chưa rõ có charter khám phá cụ thể.
- [ ] Tỷ trọng hai cách tiếp cận dựa trên rủi ro, độ ổn định và mức độ hiểu biết.
- [ ] Phiên khám phá có phạm vi, timebox, dữ liệu và điều kiện môi trường.
- [ ] Người thực hiện ghi lại đường đi, quan sát và bằng chứng cần thiết.
- [ ] Phát hiện được tái hiện và phân loại trước khi chuyển xử lý.
- [ ] Lỗi quan trọng đã sửa được chuyển thành regression test ở tầng phù hợp.
- [ ] Yêu cầu, phạm vi và danh mục rủi ro được cập nhật từ kết quả khám phá.
- [ ] Kịch bản không bị nhân bản chỉ để lưu mọi thao tác đã thử.
- [ ] Có debrief và người phụ trách cho hành động tiếp theo.
- [ ] Hiệu quả được đánh giá bằng chất lượng phát hiện và bằng chứng, không chỉ số lượng test.

## Kết luận

Kiểm thử có kịch bản tạo bằng chứng nhất quán cho hành vi đã biết và hỗ trợ hồi quy; kiểm thử khám phá giúp tìm hiểu sản phẩm, kiểm tra giả thuyết và phát hiện tình huống chưa được dự đoán. Cần ưu tiên kịch bản cho yêu cầu ổn định và luồng quan trọng, đồng thời dành thời gian khám phá cho tính năng mới, vùng phức tạp và rủi ro chưa rõ. Khi các phiên khám phá được tổ chức có mục tiêu, ghi nhận đầy đủ và chuyển phát hiện quan trọng thành kiểm thử hồi quy, hai cách tiếp cận sẽ bổ sung cho nhau và cải thiện chất lượng bằng chứng trong suốt vòng đời phát triển.
