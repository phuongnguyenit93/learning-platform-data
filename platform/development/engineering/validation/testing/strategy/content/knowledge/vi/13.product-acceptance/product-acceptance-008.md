# Đánh giá tiêu chí chưa rõ hoặc chưa có bằng chứng

Tiêu chí chấp nhận giúp nhóm quyết định một sản phẩm, tính năng hoặc increment đã đáp ứng nhu cầu hay chưa. Nhưng một tiêu chí chỉ hữu ích khi mọi bên hiểu cùng một ý nghĩa, có thể kiểm tra trong điều kiện xác định và có bằng chứng đủ tin cậy để đưa ra quyết định. Những câu như “hệ thống phải nhanh”, “giao diện dễ dùng”, “dữ liệu phải chính xác” hoặc “chức năng hoạt động ổn định” chưa đủ để kết luận đạt hay không đạt nếu không có phạm vi, cách đo và ngưỡng cụ thể.

Trong quá trình nghiệm thu, nhóm thường gặp hai vấn đề khác nhau: tiêu chí chưa rõ nên không biết cần kiểm tra điều gì; hoặc tiêu chí đã rõ nhưng chưa có bằng chứng để chứng minh kết quả. Cần nhận diện đúng loại khoảng trống, làm rõ với người có thẩm quyền, xác định phương pháp xác minh và ghi nhận quyết định. Không nên tự đặt ra một ngưỡng kỹ thuật thay cho thỏa thuận nghiệp vụ, cũng không nên coi việc chưa có lỗi được báo cáo là bằng chứng sản phẩm đã đạt.

## 1. Phân biệt tiêu chí mơ hồ, không thể kiểm chứng và thiếu bằng chứng

Trước tiên, hãy xác định vấn đề nằm ở câu chữ của tiêu chí, khả năng kiểm tra hay hồ sơ kết quả.

| Tình trạng | Dấu hiệu | Ví dụ | Việc cần làm |
|---|---|---|---|
| Mơ hồ | Có nhiều cách hiểu hợp lý | “Trang phải tải nhanh” | Làm rõ đối tượng đo, điều kiện và ngưỡng |
| Thiếu phạm vi | Không nói rõ chức năng, người dùng hoặc môi trường nào áp dụng | “Hỗ trợ trình duyệt phổ biến” | Xác định danh sách hoặc chính sách môi trường |
| Không thể quan sát | Mô tả ý định hoặc cảm nhận nhưng không nêu dấu hiệu đánh giá | “Quy trình phải thân thiện” | Chuyển thành nhiệm vụ, hành vi hoặc phương pháp đánh giá có thể quan sát |
| Không thể đo trong điều kiện hiện tại | Tiêu chí có vẻ cụ thể nhưng thiếu công cụ, dữ liệu hoặc môi trường | “Độ trễ p95 dưới ngưỡng đã thống nhất” nhưng không có telemetry | Chuẩn bị phương tiện đo và môi trường phù hợp |
| Mâu thuẫn | Hai tiêu chí hoặc hai nguồn yêu cầu dẫn đến kết quả khác nhau | Một tài liệu yêu cầu lưu dữ liệu, tài liệu khác yêu cầu xóa ngay | Xác định nguồn có thẩm quyền và xin quyết định |
| Thiếu bằng chứng | Tiêu chí rõ nhưng chưa có kết quả xác minh | Có yêu cầu phân quyền nhưng chưa chạy kiểm thử truy cập chéo | Lập kế hoạch kiểm tra và thu thập bằng chứng |
| Bằng chứng không phù hợp | Có báo cáo nhưng khác phiên bản, môi trường hoặc dữ liệu yêu cầu | Test pass trên build cũ | Chạy lại trên đối tượng nghiệm thu thực tế |
| Bằng chứng không đủ tin cậy | Kết quả không lặp lại, mẫu quá nhỏ hoặc test không ổn định | Một lần đo tải không đại diện cho tải mục tiêu | Tăng chất lượng phép đo và xác minh |

Một tiêu chí có thể thuộc nhiều tình trạng cùng lúc. Ví dụ, yêu cầu “không có lỗi nghiêm trọng” vừa cần định nghĩa mức nghiêm trọng, vừa cần xác định phạm vi kiểm thử và thời điểm chốt danh sách lỗi.

Hãy ghi nhận chính xác khoảng trống. “Chưa đạt” có nghĩa đã có bằng chứng cho thấy tiêu chí không được đáp ứng. “Chưa xác minh” có nghĩa chưa đủ bằng chứng để kết luận. Hai trạng thái này dẫn đến quyết định khác nhau.

## 2. Xác định nguồn và thẩm quyền của tiêu chí

Tiêu chí chấp nhận có thể đến từ yêu cầu sản phẩm, câu chuyện người dùng, hợp đồng, SLA, quy định, tài liệu thiết kế, tiêu chuẩn nội bộ hoặc quyết định trong buổi refinement. Các nguồn có thể khác nhau về phạm vi và thẩm quyền.

Với mỗi tiêu chí, hãy xác định:

- Nguồn tài liệu hoặc quyết định tạo ra tiêu chí.
- Phiên bản, ngày hiệu lực và phạm vi áp dụng.
- Người đề xuất, người xác nhận và người có quyền chấp thuận ngoại lệ.
- Sản phẩm, tính năng, gói dịch vụ, nhóm người dùng hoặc môi trường liên quan.
- Mối liên hệ với yêu cầu cấp cao, rủi ro và nghĩa vụ hợp đồng.
- Các tiêu chí khác có thể bị ảnh hưởng.

Khi có nhiều nguồn, không tự chọn câu chữ thuận tiện hơn. Ví dụ, một user story nói thao tác được phép trong khi phụ lục bảo mật yêu cầu vai trò cụ thể. Nhóm cần chuyển mâu thuẫn đến chủ sở hữu sản phẩm và người phụ trách nghĩa vụ liên quan để thống nhất cách hiểu.

Phân biệt yêu cầu bắt buộc với mong muốn hoặc mục tiêu cải tiến. Một ý kiến trong buổi demo có thể là phản hồi hữu ích nhưng chưa chắc đã là điều kiện nghiệm thu đã được phê duyệt. Ghi rõ trạng thái của từng nội dung để tránh mở rộng hoặc thu hẹp phạm vi nghiệm thu ngoài quyết định của các bên.

## 3. Chuyển câu chữ chung chung thành tiêu chí có thể kiểm chứng

Một tiêu chí tốt cần mô tả điều kiện, hành động hoặc đối tượng, kết quả mong đợi và cách xác minh. Tùy loại yêu cầu, có thể cần thêm ngưỡng, thời điểm, mẫu dữ liệu và môi trường.

Ví dụ:

| Câu chữ chưa rõ | Câu hỏi cần làm rõ | Dạng tiêu chí có thể kiểm chứng |
|---|---|---|
| Hệ thống phải nhanh | Luồng nào, tải nào, đo ở đâu và dùng chỉ số nào? | Với kịch bản tải và môi trường đã thống nhất, độ trễ p95 của API được đo bằng công cụ đã chọn không vượt ngưỡng được phê duyệt |
| Giao diện dễ sử dụng | Người dùng nào, nhiệm vụ nào và mức hoàn thành ra sao? | Người dùng thuộc nhóm mục tiêu hoàn thành các nhiệm vụ xác định mà không cần trợ giúp theo phương pháp đánh giá đã thống nhất |
| Dữ liệu phải chính xác | Trường nào, quy tắc tính nào và đối chiếu với nguồn nào? | Tổng đơn hàng khớp với quy tắc tính đã phê duyệt trên tập dữ liệu đại diện, gồm các trường hợp biên |
| Hệ thống ổn định | Trong khoảng thời gian và điều kiện nào? | Tỷ lệ lỗi và thời gian gián đoạn được đo trong cửa sổ quan sát đã xác định, theo ngưỡng được duyệt |
| Bảo mật tốt | Tài sản, ranh giới tin cậy và mối đe dọa nào? | Các kiểm tra phân quyền, xác thực và truy cập chéo theo danh sách kịch bản bắt buộc đều đạt |
| Hỗ trợ nhiều thiết bị | Thiết bị, hệ điều hành và phiên bản nào? | Các tổ hợp trong ma trận môi trường được phê duyệt vượt qua tập kiểm thử tương ứng |

Các ngưỡng trong ví dụ phải do bên có thẩm quyền thống nhất dựa trên nhu cầu, rủi ro và điều kiện thực tế. Người kiểm thử có thể đề xuất cách đo hoặc đưa ra dữ liệu tham khảo, nhưng không nên tự biến một con số thuận tiện thành cam kết nghiệm thu.

### 3.1. Dùng cấu trúc điều kiện – hành động – kết quả

Với yêu cầu chức năng, có thể diễn đạt theo cấu trúc:

- **Điều kiện ban đầu:** trạng thái hệ thống, vai trò, dữ liệu và môi trường.
- **Hành động:** thao tác của người dùng hoặc sự kiện từ hệ thống.
- **Kết quả mong đợi:** phản hồi, thay đổi trạng thái, dữ liệu và tác dụng phụ được phép hoặc bị cấm.

Ví dụ:

**Điều kiện:** người dùng đã đăng nhập nhưng không có quyền quản trị đơn hàng.

**Hành động:** người dùng gửi yêu cầu thay đổi trạng thái đơn hàng qua API.

**Kết quả mong đợi:** hệ thống từ chối thao tác, trạng thái đơn hàng không thay đổi và sự kiện bị từ chối được ghi nhận theo chính sách kiểm toán.

Cấu trúc này giúp tiêu chí rõ hơn và có thể chuyển thành test case. Nó cũng làm lộ những phần còn thiếu, chẳng hạn chưa xác định mã phản hồi, nội dung thông báo hoặc yêu cầu ghi log.

### 3.2. Xác định ngưỡng và điều kiện đo

Với tiêu chí định lượng, cần thống nhất:

- Chỉ số đo và đơn vị.
- Điểm bắt đầu, điểm kết thúc và cách tính.
- Môi trường, cấu hình, thiết bị và dữ liệu.
- Tải, số lượng người dùng, tần suất hoặc thời gian quan sát.
- Phân vị hoặc cách tổng hợp, nếu có.
- Số lần chạy và cách xử lý ngoại lệ.
- Ngưỡng đạt, ngưỡng cảnh báo và điều kiện không đạt.

Ví dụ, “thời gian phản hồi dưới 2 giây” vẫn chưa đủ nếu chưa rõ đo ở client hay server, với dữ liệu nào, ở mức tải nào và dùng trung bình hay p95. Trung bình có thể che khuất một nhóm yêu cầu rất chậm; lựa chọn chỉ số phải phản ánh trải nghiệm hoặc mục tiêu vận hành thực tế.

### 3.3. Xác định cách đánh giá với tiêu chí định tính

Một số yêu cầu như khả năng sử dụng, tính dễ hiểu hoặc mức phù hợp của nội dung không thể được đánh giá chỉ bằng một assertion tự động. Tuy nhiên, chúng vẫn có thể được kiểm chứng bằng phương pháp có cấu trúc.

Hãy xác định:

- Nhóm người tham gia hoặc vai trò đánh giá.
- Nhiệm vụ hoặc tình huống cần thực hiện.
- Hướng dẫn và điều kiện đánh giá.
- Dấu hiệu quan sát, câu hỏi hoặc thang đánh giá.
- Cách ghi nhận ý kiến và xử lý khác biệt.
- Ai có quyền xác nhận kết quả.

Không nên ghi “người dùng thấy ổn” mà không có thông tin về ai đã đánh giá, họ thực hiện nhiệm vụ gì và kết quả được tổng hợp như thế nào.

## 4. Làm rõ tiêu chí với đúng người có thẩm quyền

Khi tiêu chí mơ hồ, người kiểm thử không nên tự diễn giải thành cam kết. Hãy chuẩn bị câu hỏi có ngữ cảnh và đề xuất các cách hiểu để người có thẩm quyền lựa chọn.

Một cuộc trao đổi làm rõ nên có:

1. Trích dẫn tiêu chí hiện tại và nguồn của nó.
2. Nêu điểm mơ hồ hoặc mâu thuẫn cụ thể.
3. Đưa ra các tình huống có thể dẫn đến cách hiểu khác nhau.
4. Giải thích tác động đến thiết kế, kiểm thử, thời gian và quyết định nghiệm thu.
5. Đề xuất cách diễn đạt hoặc phương pháp đo.
6. Yêu cầu người có thẩm quyền xác nhận và ghi lại quyết định.

Ví dụ, với câu “hỗ trợ tải lên tệp lớn”, nhóm có thể hỏi kích thước tối đa, định dạng, số tệp đồng thời, hành vi khi mất kết nối, thời gian xử lý và quyền truy cập. Có thể đề xuất một bảng cấu hình để chủ sở hữu sản phẩm xác nhận thay vì hỏi một câu chung chung.

Nếu các bên chưa thống nhất, ghi trạng thái “cần làm rõ”, người phụ trách và thời hạn quyết định. Nếu tiêu chí ảnh hưởng đến an toàn, bảo mật, dữ liệu hoặc nghĩa vụ hợp đồng, chuyển đến đúng chủ sở hữu chuyên môn. Không được dùng giả định tạm thời làm căn cứ kết luận nghiệm thu cuối cùng.

## 5. Phân biệt tiêu chí chấp nhận với tiêu chí kết thúc kiểm thử

Hai loại tiêu chí có liên quan nhưng trả lời các câu hỏi khác nhau.

- **Tiêu chí chấp nhận (acceptance criteria):** điều kiện một tính năng, yêu cầu hoặc sản phẩm cần đáp ứng để được bên liên quan chấp nhận.
- **Tiêu chí kết thúc kiểm thử (exit criteria):** điều kiện để kết thúc một hoạt động hoặc giai đoạn kiểm thử, dựa trên phạm vi và bằng chứng đã thống nhất.
- **Definition of Done:** thỏa thuận của nhóm về điều kiện một hạng mục hoặc increment được xem là hoàn thành.
- **Điều kiện phát hành:** các yêu cầu và quyết định cần có trước khi triển khai cho người dùng.

Ví dụ, tiêu chí chấp nhận của chức năng hoàn tiền có thể yêu cầu số tiền hoàn đúng và chỉ vai trò được phép mới thực hiện được. Exit criteria của đợt kiểm thử có thể yêu cầu các kịch bản hoàn tiền bắt buộc đã chạy, không còn lỗi nghiêm trọng chưa được xử lý và bằng chứng đã được lưu. Điều kiện phát hành có thể bổ sung phê duyệt rủi ro, kế hoạch giám sát và phương án quay lui.

Một sản phẩm có thể có tiêu chí chấp nhận rõ nhưng chưa đủ bằng chứng để kết luận. Ngược lại, một đợt kiểm thử có thể hoàn tất theo kế hoạch nhưng phát hiện tiêu chí chấp nhận chưa được đáp ứng. Cần báo cáo riêng hai trạng thái này.

## 6. Xác định bằng chứng phù hợp cho từng tiêu chí

Bằng chứng cần trực tiếp hỗ trợ kết luận. Không phải tài liệu nào có liên quan cũng chứng minh tiêu chí đã đạt.

| Loại tiêu chí | Bằng chứng có thể phù hợp | Giới hạn cần xem xét |
|---|---|---|
| Chức năng | Kết quả test case, log, trạng thái dữ liệu và bản ghi giao dịch | Cần đúng phiên bản, dữ liệu và điều kiện |
| Hiệu năng | Báo cáo tải, độ trễ, thông lượng và tài nguyên | Phải ghi rõ tải, môi trường, thời lượng và phương pháp đo |
| Bảo mật | Kết quả kiểm thử phân quyền, rà soát cấu hình, báo cáo đánh giá | Một lần quét không chứng minh toàn bộ hệ thống an toàn |
| Tính toàn vẹn dữ liệu | Đối chiếu nguồn và đích, truy vấn kiểm tra, báo cáo reconciliation | Cần định nghĩa nguồn chuẩn, tập dữ liệu và sai số cho phép |
| Khả năng sử dụng | Quan sát nhiệm vụ, kết quả đánh giá và phản hồi người dùng | Cần mô tả nhóm tham gia và phương pháp |
| Khả năng tương thích | Kết quả trên ma trận thiết bị, trình duyệt và phiên bản | Không đại diện cho tổ hợp ngoài ma trận |
| Khả năng phục hồi | Biên bản restore drill, thời gian khôi phục và dữ liệu sau phục hồi | Cần điều kiện diễn tập tương ứng mục tiêu thực tế |

Một bằng chứng tốt cần có đủ thông tin để người khác xem lại:

- Mã tiêu chí hoặc yêu cầu được xác minh.
- Phiên bản build, commit hoặc release.
- Môi trường và cấu hình.
- Dữ liệu và điều kiện thực hiện.
- Công cụ, phương pháp và thời điểm.
- Kết quả mong đợi và kết quả quan sát.
- Người thực hiện hoặc nguồn tạo bằng chứng.
- Liên kết đến báo cáo, log, ảnh chụp hoặc biên bản.
- Giới hạn, sai lệch và kết luận.

Ảnh chụp màn hình có thể chứng minh một trạng thái giao diện tại một thời điểm, nhưng không tự chứng minh tính toàn vẹn dữ liệu, phân quyền phía máy chủ hay hiệu năng. Hãy chọn bằng chứng phù hợp với bản chất tiêu chí.

## 7. Đánh giá chất lượng và độ đầy đủ của bằng chứng

Có báo cáo không đồng nghĩa có đủ bằng chứng. Trước khi kết luận, hãy kiểm tra tính liên quan, tính đại diện, tính toàn vẹn và khả năng truy vết.

### 7.1. Bằng chứng có đúng đối tượng không?

Xác minh bằng chứng được tạo từ đúng build, commit, cấu hình và thành phần nằm trong phạm vi nghiệm thu. Kết quả của bản dựng trước khi sửa lỗi không chứng minh phiên bản mới đã đạt. Báo cáo từ môi trường staging khác biệt đáng kể với production cần nêu rõ giới hạn.

### 7.2. Bằng chứng có bao phủ điều kiện quan trọng không?

Một test case thành công trên dữ liệu bình thường không đủ chứng minh các trường hợp biên, quyền bị từ chối, lỗi phụ thuộc hoặc thao tác đồng thời. So sánh bằng chứng với từng phần của tiêu chí và danh sách rủi ro.

### 7.3. Bằng chứng có đáng tin và lặp lại được không?

Kiểm tra test có ổn định, công cụ có cấu hình đúng và dữ liệu có thể tái tạo không. Với phép đo định lượng, cần xem số lần chạy, độ biến thiên và điều kiện môi trường. Với đánh giá định tính, cần xem phương pháp và cách tổng hợp kết quả.

### 7.4. Bằng chứng có còn hiệu lực không?

Một báo cáo có thể đã cũ sau khi thay đổi mã nguồn, cấu hình, dependency hoặc dữ liệu. Xác định sự kiện nào làm bằng chứng mất hiệu lực và cần chạy lại phép kiểm tra nào.

### 7.5. Có thể truy vết từ tiêu chí đến kết quả không?

Mỗi tiêu chí cần liên kết với một hoặc nhiều test, hoạt động rà soát, báo cáo hoặc biên bản. Nếu một kết quả không thể nối với tiêu chí cụ thể, người ra quyết định khó biết nó chứng minh điều gì.

## 8. Xử lý khi tiêu chí rõ nhưng chưa có bằng chứng

Đây là khoảng trống thực thi. Nhóm đã biết cần chứng minh điều gì nhưng chưa thực hiện hoặc chưa lưu kết quả phù hợp.

Một quy trình xử lý:

1. Xác định chính xác tiêu chí và phần chưa có bằng chứng.
2. Tìm nguyên nhân: thiếu môi trường, dữ liệu, quyền, công cụ, người thực hiện hay thời gian.
3. Xác định phương pháp kiểm tra phù hợp và mức độ độc lập cần thiết.
4. Chuẩn bị điều kiện, dữ liệu và người chịu trách nhiệm.
5. Thực hiện kiểm tra trên đúng phiên bản và phạm vi.
6. Lưu kết quả và đánh giá giới hạn.
7. Cập nhật trạng thái tiêu chí và báo cáo khoảng trống còn lại.

Không nên thay bằng chứng còn thiếu bằng một tuyên bố như “chức năng đã được demo” nếu tiêu chí yêu cầu kiểm tra quyền, tải hoặc dữ liệu. Demo có thể là bằng chứng cho luồng thao tác, nhưng không nhất thiết chứng minh các thuộc tính khác.

Nếu không thể thu thập bằng chứng trước mốc phát hành, hãy đưa ra quyết định có kiểm soát: hoãn phát hành, giới hạn phạm vi, bổ sung biện pháp giảm thiểu hoặc xin chấp nhận rủi ro theo đúng thẩm quyền. Ghi rõ ai chấp thuận, lý do, tác động, thời hạn và hành động tiếp theo. Trạng thái phải là “chưa xác minh” hoặc “ngoại lệ được chấp thuận”, không phải “đạt”.

## 9. Xử lý khi tiêu chí không thể kiểm chứng như hiện tại

Đôi khi yêu cầu mô tả một kết quả mong muốn nhưng không có phương pháp đo trực tiếp. Ví dụ, “sản phẩm phải tạo cảm giác tin cậy” không phải một phép thử có kết quả pass/fail rõ ràng.

Có thể xử lý theo các hướng:

- Chia mục tiêu rộng thành các thuộc tính quan sát được.
- Xác định hành vi hoặc nhiệm vụ đại diện.
- Chọn chỉ số hoặc phương pháp đánh giá phù hợp.
- Dùng đánh giá chuyên gia hoặc người dùng theo quy trình có cấu trúc.
- Xác định giới hạn của phương pháp và cách kết hợp nhiều nguồn bằng chứng.
- Xin chủ sở hữu yêu cầu xác nhận cách diễn giải mới.

Không phải mọi tiêu chí đều cần chuyển thành một con số. Với yêu cầu về nội dung, khả năng sử dụng hoặc chất lượng thiết kế, một rubric có mô tả mức đạt, ví dụ minh họa và người đánh giá có thẩm quyền có thể phù hợp hơn một ngưỡng số giả tạo.

Nếu tiêu chí không thể kiểm chứng vì phụ thuộc một sự kiện tương lai, chẳng hạn khả năng chịu tải trong mùa cao điểm chưa đến, hãy xác định bằng chứng thay thế có thể thu thập trước phát hành, mức tin cậy của mô phỏng và hoạt động giám sát sau triển khai. Ghi rõ điều gì vẫn chưa được chứng minh.

## 10. Quản lý tiêu chí mâu thuẫn và thay đổi trong quá trình nghiệm thu

Mâu thuẫn có thể xuất hiện giữa yêu cầu sản phẩm, hợp đồng, thiết kế, tiêu chí chấp nhận và chính sách vận hành. Thay đổi yêu cầu sau khi kiểm thử bắt đầu cũng có thể khiến kết quả cũ không còn phù hợp.

Khi phát hiện mâu thuẫn:

1. Ghi lại các nguồn và câu chữ liên quan.
2. Xác định phạm vi, bên bị ảnh hưởng và hậu quả của từng cách hiểu.
3. Tìm người có thẩm quyền giải quyết.
4. Đề xuất cách diễn đạt hoặc phương án đáp ứng.
5. Ghi quyết định, người phê duyệt và ngày hiệu lực.
6. Cập nhật tiêu chí, test case, ma trận truy vết và kế hoạch kiểm thử.
7. Đánh giá lại bằng chứng đã thu thập.

Khi tiêu chí thay đổi, không được mặc định rằng kết quả cũ vẫn chứng minh yêu cầu mới. Hãy phân tích phần nào còn hiệu lực, phần nào cần chạy lại và phần nào cần được đánh giá lại bởi bên liên quan.

Duy trì lịch sử thay đổi để có thể trả lời tiêu chí nào đã được áp dụng cho lần nghiệm thu cụ thể. Nếu hai bên thống nhất một ngoại lệ, ghi rõ phạm vi và thời hạn để không biến ngoại lệ thành quy tắc mặc định.

## 11. Theo dõi trạng thái tiêu chí và ma trận truy vết

Có thể quản lý trạng thái theo từng tiêu chí:

| Trạng thái | Ý nghĩa | Điều kiện chuyển tiếp |
|---|---|---|
| Draft | Tiêu chí đang được soạn | Có nội dung đủ rõ để rà soát |
| Needs Clarification | Chưa rõ hoặc có mâu thuẫn | Chủ sở hữu xác nhận cách hiểu |
| Ready to Verify | Đã rõ và có phương pháp xác minh | Môi trường, dữ liệu và người thực hiện sẵn sàng |
| In Verification | Đang thu thập bằng chứng | Có kết quả hoặc vấn đề cần điều tra |
| Passed | Bằng chứng phù hợp cho thấy tiêu chí đạt | Được người có trách nhiệm xem xét |
| Failed | Bằng chứng cho thấy tiêu chí không đạt | Có hành động khắc phục và kiểm tra lại |
| Not Verified | Chưa có hoặc chưa đủ bằng chứng | Có kế hoạch xác minh hoặc quyết định ngoại lệ |
| Accepted Exception | Rủi ro được chấp nhận theo thẩm quyền | Có người phê duyệt, lý do và ngày xem lại |

Một ma trận truy vết tối thiểu có thể gồm:

| ID tiêu chí | Nguồn | Cách diễn giải đã duyệt | Phương pháp xác minh | Bằng chứng | Trạng thái | Chủ sở hữu |
|---|---|---|---|---|---|---|
| AC-01 | Yêu cầu chức năng | Hành vi cần đạt trong điều kiện xác định | Test case hoặc demo có kiểm soát | Báo cáo test / biên bản | Passed / Failed / Not Verified | Người phụ trách |
| AC-02 | Yêu cầu hiệu năng | Chỉ số, tải và ngưỡng được phê duyệt | Kiểm thử tải | Báo cáo đo | Trạng thái tương ứng | Người phụ trách |
| AC-03 | Yêu cầu bảo mật | Quyền và tài sản cần bảo vệ | Kiểm thử phân quyền | Kết quả security test | Trạng thái tương ứng | Người phụ trách |

Mỗi hàng cần liên kết đến bằng chứng thực tế thay vì chỉ ghi “đã test”. Khi có thay đổi, ma trận giúp xác định tiêu chí, phép kiểm tra và quyết định nào cần cập nhật.

## 12. Ví dụ: đánh giá tiêu chí nghiệm thu cho chức năng thanh toán

Giả sử một tính năng thanh toán có bốn tiêu chí ban đầu:

- Thanh toán phải nhanh.
- Giao dịch phải chính xác.
- Chỉ người có quyền mới được hoàn tiền.
- Hệ thống phải xử lý tốt khi nhà cung cấp thanh toán bị gián đoạn.

Các câu chữ này chưa đủ để nghiệm thu. Nhóm làm rõ với chủ sở hữu sản phẩm, kỹ thuật, bảo mật và vận hành.

| Tiêu chí ban đầu | Nội dung cần xác nhận | Cách kiểm chứng sau khi làm rõ |
|---|---|---|
| Thanh toán phải nhanh | Đo từ lúc nào đến lúc nào, tải và phân vị nào, ngưỡng bao nhiêu? | Kiểm thử tải trên môi trường đại diện, lưu độ trễ và tỷ lệ lỗi |
| Giao dịch phải chính xác | Đối chiếu số tiền, trạng thái và mã giao dịch với nguồn nào? | Kiểm thử quy tắc tính tiền, retry và đối soát với nhà cung cấp |
| Chỉ người có quyền mới được hoàn tiền | Vai trò nào được phép, quyền ở cấp đơn hàng hay toàn tenant? | Kiểm thử API với vai trò hợp lệ, không hợp lệ và truy cập chéo tenant |
| Xử lý tốt khi nhà cung cấp gián đoạn | Hệ thống giữ trạng thái nào, retry ra sao và người dùng nhận thông báo gì? | Fault injection, timeout, callback trễ/lặp và kiểm thử phục hồi |

Sau khi làm rõ, nhóm cần ghi ngưỡng và điều kiện cụ thể đã được phê duyệt. Ví dụ, tiêu chí hiệu năng phải nêu tải thử, môi trường, chỉ số và ngưỡng được thống nhất. Không tự dùng một ngưỡng mẫu nếu chưa có quyết định của chủ sở hữu yêu cầu.

Trong quá trình nghiệm thu, giả sử kiểm thử chức năng và phân quyền đã đạt, nhưng kiểm thử tải chưa được thực hiện vì môi trường đo chưa sẵn sàng. Trạng thái của tiêu chí hiệu năng là “chưa xác minh”, dù các tiêu chí khác đã đạt. Người ra quyết định cần xem xét mức rủi ro, kế hoạch kiểm tra bổ sung và điều kiện phát hành. Không được gộp các kết quả thành một kết luận chung rằng toàn bộ tính năng đã đạt.

Nếu bên liên quan chấp nhận phát hành có điều kiện, hồ sơ cần nêu rõ giới hạn, người phê duyệt, biện pháp giám sát, thời hạn chạy kiểm thử tải và hành động nếu kết quả không đạt. Quyết định này phải được truy vết đến phiên bản phát hành cụ thể.

## 13. Báo cáo kết quả nghiệm thu minh bạch

Báo cáo nên giúp người đọc biết điều gì đã được xác nhận, điều gì không đạt và điều gì vẫn chưa biết.

Một báo cáo có thể gồm:

- Phạm vi, phiên bản sản phẩm và môi trường nghiệm thu.
- Danh sách tiêu chí cùng nguồn và phiên bản.
- Cách diễn giải đã được xác nhận.
- Phương pháp và bằng chứng cho từng tiêu chí.
- Kết quả đạt, không đạt hoặc chưa xác minh.
- Lỗi, giới hạn, giả định và ngoại lệ còn mở.
- Rủi ro còn lại và tác động đến người dùng.
- Người xem xét, người phê duyệt và ngày quyết định.
- Hành động tiếp theo, chủ sở hữu và thời hạn.

Không nên dùng một tỷ lệ pass tổng thể để che khuất tiêu chí trọng yếu chưa được xác minh. Nếu có 19 tiêu chí đạt và một tiêu chí bảo mật chưa chạy, báo cáo phải thể hiện rõ khoảng trống đó. Tỷ lệ chỉ là thông tin tổng hợp; quyết định nghiệm thu phụ thuộc vào bản chất và mức độ bắt buộc của từng tiêu chí.

Khi bằng chứng được tạo bởi công cụ, lưu phiên bản công cụ và cấu hình quan trọng. Khi bằng chứng là đánh giá của con người, lưu người tham gia, phương pháp, ngày thực hiện và kết luận đã thống nhất.

## 14. Checklist đánh giá tiêu chí và bằng chứng

Trước khi đưa ra kết luận nghiệm thu, hãy kiểm tra:

- Mỗi tiêu chí có nguồn, phiên bản và người xác nhận không?
- Câu chữ có một cách hiểu rõ ràng hoặc đã ghi nhận các cách hiểu được duyệt không?
- Phạm vi, điều kiện, dữ liệu, môi trường và ngưỡng đã xác định chưa?
- Tiêu chí định tính có phương pháp và rubric đánh giá phù hợp không?
- Tiêu chí chức năng có điều kiện, hành động và kết quả mong đợi không?
- Tiêu chí định lượng có chỉ số, đơn vị, cách đo và ngưỡng không?
- Bằng chứng có đúng build, cấu hình và đối tượng nghiệm thu không?
- Bằng chứng có đủ bao phủ trường hợp biên, lỗi và rủi ro quan trọng không?
- Kết quả có thể tái lập, truy vết và xem xét độc lập không?
- Mâu thuẫn hoặc thay đổi đã được người có thẩm quyền quyết định chưa?
- Tiêu chí chưa xác minh có được tách biệt với tiêu chí không đạt không?
- Ngoại lệ có người phê duyệt, lý do, biện pháp giảm thiểu và thời hạn không?
- Báo cáo có thể hiện rõ giới hạn và rủi ro còn lại không?

Sơ đồ dưới đây tóm tắt quy trình xử lý tiêu chí từ lúc nhận diện đến khi có quyết định:

~~~mermaid
flowchart TD
    A["Tiếp nhận tiêu chí và nguồn"] --> B["Đánh giá độ rõ và khả năng kiểm chứng"]
    B --> C{"Tiêu chí đã rõ?"}
    C -->|Chưa| D["Làm rõ với chủ sở hữu và ghi quyết định"]
    D --> B
    C -->|Rõ| E["Xác định phương pháp và bằng chứng cần có"]
    E --> F{"Đã có bằng chứng phù hợp?"}
    F -->|Chưa| G["Chuẩn bị và thực hiện xác minh"]
    G --> F
    F -->|Có| H["Đánh giá kết quả và giới hạn"]
    H --> I{"Đạt tiêu chí?"}
    I -->|Có| J["Ghi nhận Passed"]
    I -->|Không| K["Ghi nhận Failed và hành động khắc phục"]
    I -->|Chưa đủ| L["Ghi Not Verified hoặc xin quyết định ngoại lệ"]
    K --> E
    J --> M["Tổng hợp báo cáo nghiệm thu"]
    L --> M
~~~

Đánh giá tiêu chí chưa rõ hoặc chưa có bằng chứng là công việc bảo đảm rằng quyết định nghiệm thu dựa trên cùng một cách hiểu và dữ liệu có thể kiểm tra. Khi mỗi tiêu chí có nguồn, phạm vi, phương pháp, bằng chứng, trạng thái và người chịu trách nhiệm, nhóm có thể phân biệt rõ sản phẩm đã đạt, chưa đạt hay chưa đủ cơ sở kết luận. Sự minh bạch này giúp các bên xử lý khoảng trống trước phát hành và quản lý rủi ro còn lại một cách có trách nhiệm.

