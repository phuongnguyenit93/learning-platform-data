# Vai trò của kiểm thử trong cung cấp thông tin về chất lượng và rủi ro

Kiểm thử giúp nhóm phát triển và các bên liên quan hiểu sản phẩm đang hoạt động như thế nào, những yêu cầu nào đã được đáp ứng, những vấn đề nào đã xuất hiện và phần nào vẫn còn chưa chắc chắn. Giá trị của kiểm thử nằm ở thông tin có thể kiểm chứng mà nó tạo ra để hỗ trợ quyết định: tiếp tục phát triển, sửa lỗi, thay đổi phạm vi, chấp nhận rủi ro hay phát hành.

Kiểm thử không thể chứng minh một sản phẩm hoàn toàn không có lỗi. Một lần chạy thành công chỉ cho biết hành vi được kiểm tra đã phù hợp với kết quả mong đợi trong điều kiện cụ thể. Vì vậy, kết quả kiểm thử luôn cần được đọc cùng phạm vi, môi trường, dữ liệu, thời điểm và những giới hạn của hoạt động kiểm thử.

## 1. Chất lượng và rủi ro là hai góc nhìn liên quan

**Chất lượng** thể hiện mức độ sản phẩm đáp ứng yêu cầu, mục tiêu sử dụng và kỳ vọng hợp lý của người dùng. Chất lượng có nhiều khía cạnh: tính đúng đắn của chức năng, độ tin cậy, hiệu năng, khả năng sử dụng, tính tương thích, an toàn thông tin và khả năng bảo trì. Một sản phẩm có thể hoạt động đúng chức năng trong một tình huống nhưng vẫn gây trải nghiệm kém, phản hồi chậm hoặc khó phục hồi khi có sự cố.

**Rủi ro sản phẩm** là khả năng một vấn đề trong sản phẩm gây ra hậu quả không mong muốn. Rủi ro thường được xem xét qua hai yếu tố:

- **Khả năng xảy ra:** tình huống lỗi có thể xuất hiện thường xuyên đến mức nào hoặc có bao nhiêu điều kiện khiến nó xảy ra.
- **Mức độ tác động:** hậu quả đối với người dùng, dữ liệu, hoạt động kinh doanh, chi phí, uy tín hoặc nghĩa vụ pháp lý nếu tình huống đó xảy ra.

Có thể dùng mô hình khái niệm `rủi ro = khả năng xảy ra × mức độ tác động` để thảo luận và sắp xếp ưu tiên. Điểm số chỉ hỗ trợ trao đổi; nó không phải phép đo chính xác tuyệt đối. Một lỗi ít gặp nhưng có thể làm mất dữ liệu hoặc gây giao dịch sai vẫn có thể cần ưu tiên cao.

Kiểm thử kết nối hai góc nhìn này. Kết quả kiểm thử cho biết sản phẩm đáp ứng yêu cầu đến đâu, đồng thời cung cấp bằng chứng về các tình huống có thể gây thiệt hại. Nhờ đó, nhóm có cơ sở đánh giá chất lượng hiện tại và quyết định rủi ro còn lại có thể chấp nhận hay không.

## 2. Kiểm thử tạo ra thông tin như thế nào?

Một hoạt động kiểm thử có ý nghĩa cần có câu hỏi rõ ràng và bằng chứng có thể truy nguyên. Quy trình cơ bản gồm các bước sau:

1. **Xác định cơ sở kiểm thử:** đọc yêu cầu, tiêu chí chấp nhận, thiết kế, quy tắc nghiệp vụ, phản hồi người dùng hoặc các ràng buộc kỹ thuật liên quan. Cơ sở kiểm thử cho biết điều gì cần được xác minh.
2. **Xác định điều kiện và kết quả mong đợi:** chuyển cơ sở kiểm thử thành các tình huống, dữ liệu đầu vào, trạng thái ban đầu và kết quả cần quan sát. Kết quả mong đợi có thể đến từ yêu cầu, quy tắc nghiệp vụ, tài liệu giao diện hoặc một chuẩn đã thống nhất.
3. **Thực hiện kiểm thử trong điều kiện xác định:** chạy kiểm thử trên một phiên bản, cấu hình, môi trường và bộ dữ liệu cụ thể. Ghi nhận các điều kiện có thể ảnh hưởng đến kết quả.
4. **Thu thập quan sát:** lưu kết quả thực tế, nhật ký, thông báo lỗi, ảnh chụp, số đo hiệu năng hoặc các dấu hiệu liên quan. Bằng chứng cần đủ để người khác hiểu và kiểm tra lại.
5. **So sánh và phân tích:** đối chiếu kết quả thực tế với kết quả mong đợi, xác định sai lệch, tìm điều kiện tái hiện và đánh giá tác động.
6. **Truyền đạt kết luận cùng giới hạn:** nêu điều đã kiểm tra, điều chưa kiểm tra, vấn đề đã phát hiện và những bất định còn lại.

Trong quá trình này cần phân biệt ba khái niệm:

- **Sai sót của con người (error):** hành động hoặc quyết định không chính xác, chẳng hạn hiểu sai yêu cầu hoặc tính sai công thức.
- **Khiếm khuyết (defect):** vấn đề trong yêu cầu, thiết kế, mã nguồn, dữ liệu hoặc tài liệu có thể dẫn đến hành vi không đúng.
- **Thất bại khi chạy (failure):** hành vi sai lệch có thể quan sát được khi sản phẩm được thực thi, chẳng hạn hệ thống tính sai tổng tiền.

Kiểm thử thường phát hiện thất bại; việc phân tích sau đó giúp xác định khiếm khuyết liên quan và nguyên nhân. Không phải mọi khiếm khuyết đều biểu hiện thành thất bại trong mọi lần chạy, vì điều kiện kích hoạt có thể chưa xuất hiện.

## 3. Các loại bằng chứng cho biết điều gì?

Không có một loại kiểm thử nào trả lời được mọi câu hỏi về chất lượng. Cần chọn cách kiểm thử phù hợp với thuộc tính và rủi ro đang xem xét.

| Loại bằng chứng | Thông tin có thể thu được | Giới hạn cần lưu ý |
| --- | --- | --- |
| Kiểm thử chức năng | Chức năng có tạo ra kết quả đúng với đầu vào và điều kiện đã xác định hay không | Chỉ bao phủ các luồng, dữ liệu và điều kiện đã kiểm tra |
| Kiểm thử tích hợp | Các thành phần hoặc hệ thống bên ngoài trao đổi dữ liệu và xử lý lỗi đúng như mong đợi hay không | Phụ thuộc vào cấu hình, dữ liệu và mức độ giống thật của hệ thống tích hợp |
| Kiểm thử hiệu năng | Thời gian phản hồi, thông lượng và mức sử dụng tài nguyên dưới tải xác định | Kết quả có thể khác khi tải, dữ liệu hoặc hạ tầng thay đổi |
| Kiểm thử bảo mật | Có thể khai thác các điểm yếu hoặc vượt qua cơ chế bảo vệ trong phạm vi đã kiểm tra hay không | Không một lượt kiểm thử nào bao phủ toàn bộ mối đe dọa |
| Kiểm thử khả năng sử dụng | Người dùng có hoàn thành tác vụ dễ dàng, hiểu phản hồi và tránh nhầm lẫn hay không | Cần chọn người tham gia và bối cảnh phù hợp; quan sát có thể chịu ảnh hưởng bởi mẫu thử |
| Kiểm thử thăm dò | Những hành vi bất ngờ, luồng ít được mô tả hoặc vấn đề phát sinh khi kết hợp nhiều điều kiện | Cần ghi lại đường đi và bằng chứng để kết quả có thể được xem xét, tái hiện |
| Độ bao phủ và phân tích tĩnh | Phần mã, nhánh, yêu cầu hoặc quy tắc đã được xem xét; một số vấn đề có thể nhận diện mà không chạy chương trình | Độ bao phủ cao không đồng nghĩa mọi hành vi đều đúng; công cụ tĩnh cũng có giới hạn phát hiện |

Ví dụ, tỷ lệ độ bao phủ câu lệnh cho biết phần nào của mã đã được thực thi trong một bộ kiểm thử. Chỉ số này không chứng minh rằng các kết quả được xác minh đúng, các trường hợp biên đã được kiểm tra hay mọi rủi ro quan trọng đã được xử lý. Cần kết hợp nó với chất lượng thiết kế kiểm thử và bằng chứng về hành vi.

## 4. Đọc kết quả kiểm thử một cách chính xác

Kết quả của từng trường hợp kiểm thử cần được diễn giải theo đúng ý nghĩa:

- **Đạt (pass):** kết quả quan sát phù hợp với kết quả mong đợi trong điều kiện đã kiểm tra. Đây là bằng chứng hỗ trợ cho hành vi đó, không phải lời khẳng định toàn bộ chức năng hoặc sản phẩm không có lỗi.
- **Không đạt (fail):** có sai lệch giữa kết quả thực tế và kết quả mong đợi. Cần lưu bằng chứng, xác minh khả năng tái hiện và phân tích mức độ ảnh hưởng trước khi kết luận nguyên nhân.
- **Bị chặn (blocked):** chưa thể thực hiện hoặc kết luận do thiếu môi trường, dữ liệu, quyền truy cập, phụ thuộc hoặc điều kiện cần thiết. Trường hợp này không cung cấp bằng chứng rằng hành vi đạt yêu cầu.
- **Chưa thực hiện (not run):** chưa có dữ liệu kiểm thử cho trường hợp đó. Không được tính như một kết quả đạt.
- **Không ổn định (flaky):** cùng một kiểm thử có thể cho kết quả khác nhau khi điều kiện được cho là tương đương. Cần điều tra nguyên nhân như phụ thuộc thời gian, dữ liệu dùng chung, thứ tự chạy hoặc môi trường.

Để kết quả có thể sử dụng được, báo cáo nên gắn với phiên bản hoặc mã build, môi trường, cấu hình, dữ liệu kiểm thử và thời điểm thực hiện. Nếu các điều kiện thay đổi đáng kể, bằng chứng cũ có thể không còn đại diện cho phiên bản hiện tại.

Các chỉ số tổng hợp như tỷ lệ đạt, số lỗi theo mức độ nghiêm trọng, xu hướng lỗi qua các phiên bản hoặc độ bao phủ giúp nhìn thấy bức tranh chung. Tuy nhiên, không nên dùng một chỉ số riêng lẻ làm đại diện cho chất lượng. Chẳng hạn, tỷ lệ đạt cao vẫn có thể che giấu một luồng thanh toán quan trọng chưa được kiểm thử.

## 5. Dùng rủi ro để chọn ưu tiên kiểm thử

Thời gian và nguồn lực kiểm thử luôn có giới hạn. Chiến lược kiểm thử cần tập trung vào những nơi mà thất bại có khả năng gây hậu quả lớn hoặc nơi nhóm còn ít thông tin. Cách tiếp cận này thường được gọi là kiểm thử dựa trên rủi ro.

Một vòng lặp thực hành có thể triển khai như sau:

1. **Nhận diện rủi ro:** liệt kê những điều có thể xảy ra sai, điều kiện kích hoạt và đối tượng có thể bị ảnh hưởng.
2. **Ước lượng và xếp hạng:** xem xét khả năng xảy ra, mức độ tác động, phạm vi ảnh hưởng và mức độ chưa chắc chắn. Dùng thang định tính hoặc điểm số đơn giản nếu cần, nhưng ghi rõ giả định.
3. **Chọn bằng chứng cần thu thập:** quyết định luồng, dữ liệu, môi trường, kỹ thuật và loại kiểm thử có thể làm giảm bất định về rủi ro.
4. **Thực hiện và cập nhật đánh giá:** khi phát hiện lỗi, thay đổi yêu cầu hoặc có dữ liệu mới, điều chỉnh mức ưu tiên và phạm vi kiểm thử.
5. **Đánh giá rủi ro còn lại:** xác định phần nào đã có bằng chứng, phần nào chưa được kiểm tra và ai có thẩm quyền chấp nhận rủi ro còn lại.

Các yếu tố thường làm tăng ưu tiên gồm:

- Chức năng ảnh hưởng trực tiếp đến tiền, dữ liệu cá nhân, quyền truy cập hoặc tính toàn vẹn dữ liệu.
- Luồng được sử dụng thường xuyên hoặc có nhiều người dùng phụ thuộc.
- Thành phần mới, phức tạp, thay đổi nhiều hoặc có lịch sử phát sinh lỗi.
- Tích hợp với dịch vụ bên ngoài, nơi nhóm khó kiểm soát hành vi và khả năng sẵn sàng.
- Lỗi khó phát hiện, khó khôi phục hoặc có tác động lan rộng.
- Yêu cầu chưa rõ, có nhiều cách diễn giải hoặc thiếu bằng chứng từ môi trường thực tế.

| Rủi ro cần xem xét | Bằng chứng kiểm thử phù hợp |
| --- | --- |
| Tính tổng đơn hàng sai khi áp dụng nhiều ưu đãi | Kiểm thử bảng kết hợp dữ liệu, biên giá trị và quy tắc tính tiền |
| Giao dịch bị ghi nhận hai lần khi người dùng thử lại | Kiểm thử lặp yêu cầu, gửi lại thông điệp và xử lý tính duy nhất của giao dịch |
| Dữ liệu mất khi dịch vụ phụ thuộc bị gián đoạn | Kiểm thử lỗi tích hợp, timeout, khôi phục và đối soát dữ liệu |
| Hệ thống chậm khi có nhiều người dùng đồng thời | Kiểm thử tải, kiểm thử sức chịu đựng và theo dõi tài nguyên |
| Người dùng không nhận biết trạng thái giao dịch | Kiểm thử khả năng sử dụng và kiểm tra nội dung thông báo ở các trạng thái khác nhau |

Kiểm thử dựa trên rủi ro không có nghĩa là bỏ qua các phần còn lại. Nó giúp giải thích vì sao một số kiểm thử được thực hiện trước, vì sao một số phạm vi cần thêm bằng chứng và phần nào đang được chấp nhận với mức rủi ro đã biết.

## 6. Ví dụ: đánh giá chất lượng và rủi ro của luồng thanh toán

Giả sử một cửa hàng trực tuyến bổ sung luồng thanh toán có mã giảm giá và kết nối với cổng thanh toán bên ngoài. Nhóm cần biết luồng có tính đúng số tiền, ghi nhận giao dịch nhất quán và phản hồi rõ ràng khi dịch vụ gặp sự cố hay không.

| Tình huống | Cách kiểm thử | Thông tin thu được và rủi ro được xem xét |
| --- | --- | --- |
| Đơn hàng có sản phẩm, phí giao hàng và mã giảm giá | Kiểm tra nhiều tổ hợp giá trị, mức giảm tối đa và điều kiện không đủ áp dụng | Xác nhận quy tắc tính tiền; phát hiện nguy cơ thu thiếu hoặc thu thừa |
| Người dùng nhấn nút thanh toán nhiều lần | Gửi nhiều yêu cầu tương đương và kiểm tra số giao dịch được tạo | Đánh giá nguy cơ tạo giao dịch trùng hoặc thu tiền nhiều lần |
| Cổng thanh toán phản hồi chậm hoặc timeout | Mô phỏng phản hồi chậm, mất kết nối và gửi lại yêu cầu | Kiểm tra cách hệ thống xác định trạng thái chưa rõ và tránh ghi nhận sai |
| Cổng thanh toán báo thành công nhưng cập nhật đơn hàng bị lỗi | Kiểm tra xử lý thông điệp, thử lại và đối soát trạng thái | Đánh giá nguy cơ tiền đã được thu nhưng đơn hàng không được cập nhật |
| Người dùng thanh toán trên thiết bị di động với mạng yếu | Kiểm tra thời gian phản hồi, trạng thái chờ và thông báo lỗi | Đánh giá khả năng hoàn thành tác vụ và mức độ rõ ràng của phản hồi |

Sau khi chạy kiểm thử, giả sử nhóm thấy các trường hợp tính tiền thông thường đều đạt, nhưng khi cổng thanh toán timeout thì hệ thống có lúc tạo yêu cầu mới mà chưa xác minh trạng thái giao dịch trước đó. Kết luận phù hợp không phải là toàn bộ thanh toán đã đạt hay toàn bộ thanh toán thất bại. Bằng chứng cho thấy quy tắc tính tiền đã được kiểm tra trong các trường hợp đã chọn, đồng thời tồn tại rủi ro cụ thể về giao dịch trùng khi timeout.

Nhóm có thể mô tả phát hiện như sau:

> Khi cổng thanh toán timeout sau khi đã nhận yêu cầu, thao tác thử lại có thể tạo một giao dịch thứ hai vì hệ thống chưa xác minh trạng thái của giao dịch đầu tiên. Bằng chứng: lỗi được tái hiện trong môi trường kiểm thử với kịch bản timeout và gửi lại yêu cầu. Tác động tiềm tàng: khách hàng bị ghi nợ hai lần. Cần xử lý tính duy nhất của yêu cầu và kiểm thử lại các tình huống timeout, gửi lại và đối soát trước khi xem rủi ro này là đã được kiểm soát.

Ví dụ này cho thấy kiểm thử có thể vừa xác nhận một phần hành vi, vừa làm rõ rủi ro còn lại. Kết luận càng cụ thể thì nhóm càng dễ chọn hành động tiếp theo.

## 7. Truyền đạt kết quả để hỗ trợ quyết định

Một báo cáo kiểm thử hữu ích cần giúp người đọc trả lời: đã kiểm tra điều gì, kết quả ra sao, bằng chứng ở đâu và điều gì vẫn có thể xảy ra. Tùy quy mô dự án, báo cáo có thể ngắn hoặc chi tiết, nhưng nên có các thông tin sau:

- **Mục tiêu và phạm vi:** tính năng, yêu cầu, rủi ro hoặc tiêu chí chấp nhận được kiểm tra.
- **Phiên bản và điều kiện:** mã build, môi trường, cấu hình, dữ liệu và thời điểm kiểm thử.
- **Độ bao phủ:** các luồng, loại kiểm thử và điều kiện đã thực hiện; những phần bị loại trừ hoặc chưa thể thực hiện.
- **Kết quả:** số trường hợp đạt, không đạt, bị chặn hoặc chưa chạy; xu hướng đáng chú ý nếu có.
- **Phát hiện:** bước tái hiện, kết quả mong đợi, kết quả thực tế, bằng chứng kèm theo, mức độ ảnh hưởng và khả năng tái hiện.
- **Rủi ro còn lại:** tình huống chưa được kiểm tra, bất định, phụ thuộc bên ngoài và hậu quả có thể xảy ra.
- **Đề xuất:** hành động tiếp theo, mức ưu tiên và quyết định cần người có trách nhiệm đưa ra.

Tránh các kết luận chung chung như “chất lượng tốt” hoặc “đã kiểm thử đầy đủ” nếu không có tiêu chí và bằng chứng hỗ trợ. Nên viết rõ điều kiện và phạm vi, ví dụ: “Trong phiên bản 2.4 trên môi trường staging, 18 trường hợp của luồng đặt hàng đã đạt; hai trường hợp xử lý timeout chưa chạy do môi trường cổng thanh toán không ổn định. Rủi ro giao dịch chưa rõ trạng thái vẫn cần được đánh giá trước khi phát hành.”

Khi phát hiện lỗi, mô tả tốt giúp nhóm khác xác minh và sửa nhanh hơn. Một báo cáo lỗi nên nêu điều kiện ban đầu, các bước thực hiện, kết quả mong đợi, kết quả thực tế, tần suất tái hiện và bằng chứng liên quan. Mức độ nghiêm trọng mô tả tác động của lỗi; mức độ ưu tiên phản ánh thứ tự xử lý trong bối cảnh nguồn lực và thời hạn. Hai khái niệm này có liên quan nhưng không nhất thiết giống nhau.

## 8. Giới hạn của bằng chứng kiểm thử và những hiểu lầm thường gặp

Kiểm thử cung cấp thông tin có giá trị nhưng luôn có giới hạn. Phạm vi kiểm thử không thể bao gồm mọi tổ hợp đầu vào, trạng thái, môi trường và tương tác. Kết quả cũng phụ thuộc chất lượng yêu cầu, dữ liệu, thiết kế kiểm thử, công cụ và kỹ năng của người thực hiện.

Một số cách diễn giải sai thường gặp:

- **“Không tìm thấy lỗi nghĩa là không có lỗi.”** Kết quả chỉ cho biết chưa phát hiện lỗi trong phạm vi và điều kiện đã kiểm tra. Lỗi có thể tồn tại ở trường hợp chưa được thực hiện hoặc chưa được nghĩ đến.
- **“Tỷ lệ kiểm thử đạt cao nghĩa là sản phẩm có chất lượng cao.”** Tỷ lệ đạt không thể hiện các trường hợp quan trọng đã được chọn đúng hay chưa. Một nhóm kiểm thử có thể đạt 99% nhưng bỏ sót trường hợp rủi ro nghiêm trọng.
- **“Độ bao phủ 100% chứng minh chương trình đúng.”** Độ bao phủ phản ánh mức thực thi theo một tiêu chí cụ thể; nó không đảm bảo mọi kết quả đều được xác minh hoặc mọi điều kiện đều được xem xét.
- **“Một lần kiểm thử đạt có thể áp dụng cho mọi phiên bản.”** Thay đổi mã, cấu hình, dữ liệu hoặc dịch vụ phụ thuộc có thể làm thay đổi hành vi. Cần xác định bằng chứng nào phải được tạo lại sau thay đổi.
- **“Mọi lỗi đều có mức độ ưu tiên như nhau.”** Cần cân nhắc tác động, khả năng xảy ra, phạm vi ảnh hưởng, khả năng khôi phục và mục tiêu phát hành.

Do đó, kết luận kiểm thử nên thể hiện mức độ tin cậy có căn cứ thay vì lời bảo đảm tuyệt đối. Khi bằng chứng chưa đủ, hãy nói rõ điều chưa biết và kiểm thử nào có thể giúp giảm bất định.

## 9. Đưa thông tin kiểm thử vào quyết định của nhóm

Thông tin kiểm thử có ích nhất khi được sử dụng xuyên suốt vòng đời phát triển:

1. **Trước khi xây dựng:** xem xét yêu cầu, xác định tiêu chí chấp nhận và nhận diện rủi ro để tránh hiểu sai ngay từ đầu.
2. **Trong khi phát triển:** kiểm thử sớm các quy tắc quan trọng, tích hợp và thay đổi có tác động lớn; phản hồi nhanh giúp giảm chi phí sửa lỗi.
3. **Trước khi phát hành:** tổng hợp bằng chứng theo phạm vi, xem xét lỗi còn mở, kiểm tra điều kiện phát hành và đánh giá rủi ro chưa được xử lý.
4. **Sau khi phát hành:** theo dõi lỗi thực tế, phản hồi người dùng và chỉ số vận hành; dùng thông tin mới để điều chỉnh giả định và chiến lược kiểm thử.

Quyết định phát hành không nên dựa trên một con số duy nhất. Nhóm cần đối chiếu kết quả với tiêu chí chấp nhận, mức độ nghiêm trọng của lỗi còn mở, rủi ro kinh doanh, khả năng giám sát và phương án khôi phục. Người có thẩm quyền chịu trách nhiệm chấp nhận rủi ro cần hiểu rõ bằng chứng và giới hạn trước khi quyết định.

## 10. Những điểm cần ghi nhớ

- Kiểm thử là hoạt động tạo bằng chứng về hành vi và chất lượng của sản phẩm trong những điều kiện xác định.
- Kết quả kiểm thử hỗ trợ nhận diện rủi ro, ưu tiên công việc và đưa ra quyết định; nó không chứng minh sản phẩm không có lỗi.
- Bằng chứng chỉ có ý nghĩa khi đi kèm phạm vi, phiên bản, môi trường, dữ liệu và giới hạn kiểm thử.
- Cần kết hợp nhiều loại kiểm thử và nhiều chỉ số; không dùng tỷ lệ đạt hoặc độ bao phủ làm đại diện duy nhất cho chất lượng.
- Ưu tiên kiểm thử dựa trên khả năng xảy ra, mức độ tác động và mức độ chưa chắc chắn của rủi ro.
- Báo cáo tốt phải nêu cả điều đã xác nhận và rủi ro còn lại để người có trách nhiệm đưa ra quyết định phù hợp.

## Câu hỏi tự kiểm tra

1. Vì sao một trường hợp kiểm thử đạt không thể chứng minh toàn bộ sản phẩm không có lỗi?
2. Hãy phân biệt chất lượng sản phẩm và rủi ro sản phẩm. Kiểm thử cung cấp thông tin cho mỗi góc nhìn như thế nào?
3. Một tính năng có tỷ lệ kiểm thử đạt 98% nhưng hai trường hợp chưa chạy liên quan đến mất dữ liệu. Bạn cần biết thêm điều gì trước khi đề xuất phát hành?
4. Vì sao độ bao phủ mã nguồn cao vẫn có thể bỏ sót rủi ro quan trọng?
5. Với một luồng nghiệp vụ bạn đang làm, hãy nêu một rủi ro có tác động lớn, một tình huống kiểm thử có thể cung cấp bằng chứng và giới hạn của bằng chứng đó.
