# Các thành phần cốt lõi: mục tiêu, phạm vi, phương pháp, nguồn lực và tiêu chí

Một chiến lược kiểm thử xác thực (validation testing strategy) mô tả cách nhóm kiểm thử thu thập bằng chứng để quyết định sản phẩm có đáp ứng nhu cầu, mục đích sử dụng và kỳ vọng chất lượng đã xác định hay không. Chiến lược liên kết mục tiêu kinh doanh với hoạt động kiểm thử cụ thể: cần chứng minh điều gì, kiểm tra phần nào, dùng cách nào, cần những nguồn lực nào và bằng chứng nào đủ để kết luận.

Năm thành phần cốt lõi của chiến lược là **mục tiêu, phạm vi, phương pháp, nguồn lực và tiêu chí**. Chúng phụ thuộc lẫn nhau. Mục tiêu định hướng phạm vi; phạm vi quyết định phương pháp; phương pháp chi phối nhu cầu nguồn lực; tiêu chí xác định khi nào bằng chứng đã đủ. Nếu một thành phần thay đổi, các thành phần còn lại cần được xem xét lại.

Trong kiểm thử phần mềm, cần phân biệt hai câu hỏi có liên quan nhưng không giống nhau:

- **Verification (xác minh):** Sản phẩm có được xây dựng đúng theo đặc tả và yêu cầu đã ghi nhận không?
- **Validation (thẩm định/xác nhận tính phù hợp):** Sản phẩm có giải quyết đúng nhu cầu và hỗ trợ đúng mục đích sử dụng của người dùng không?

Một chiến lược validation tốt kết hợp bằng chứng kỹ thuật với bằng chứng từ luồng công việc và trải nghiệm sử dụng thực tế. Kiểm thử đạt yêu cầu kỹ thuật là cần thiết, nhưng chưa đủ nếu người dùng vẫn không thể hoàn thành công việc họ cần làm.

## 1. Mục tiêu kiểm thử: cần chứng minh điều gì?

Mục tiêu là kết quả mà hoạt động kiểm thử phải làm sáng tỏ. Mục tiêu nên bắt nguồn từ nhu cầu người dùng, mục tiêu sản phẩm, yêu cầu nghiệp vụ và rủi ro có thể gây tổn thất. Câu “kiểm thử để tìm lỗi” quá chung chung; một mục tiêu hữu ích phải chỉ ra hành vi hoặc thuộc tính chất lượng cần được xác nhận và lý do nó quan trọng.

Một mục tiêu rõ ràng thường có các đặc điểm sau:

- **Gắn với kết quả sử dụng:** Nêu được người dùng cần hoàn thành việc gì và sản phẩm phải hỗ trợ ra sao.
- **Có thể kiểm chứng:** Có thể thu thập kết quả quan sát được, chẳng hạn trạng thái giao dịch, dữ liệu được lưu, phản hồi hệ thống hoặc phản hồi người dùng.
- **Ưu tiên theo rủi ro:** Tập trung vào các lỗi có thể gây mất dữ liệu, sai lệch nghiệp vụ, tổn thất tài chính, vi phạm bảo mật hoặc gián đoạn dịch vụ.
- **Phù hợp với quyết định cần đưa ra:** Bằng chứng thu được phải giúp nhóm quyết định tiếp tục phát triển, chấp nhận sản phẩm, yêu cầu sửa lỗi hay hoãn phát hành.

Ví dụ, với chức năng thanh toán của một cửa hàng trực tuyến, mục tiêu không chỉ là xác nhận nút “Thanh toán” hoạt động. Nhóm cần xác nhận rằng khách hàng có thể hoàn tất đơn hàng bằng phương thức được hỗ trợ, số tiền bị trừ chính xác, đơn hàng được tạo đúng một lần, trạng thái thanh toán được cập nhật nhất quán và người dùng nhận được thông báo phù hợp khi giao dịch thành công hoặc thất bại.

Nên diễn đạt mục tiêu ở mức kết quả, sau đó liên kết chúng với yêu cầu và kịch bản kiểm thử. Cách này giúp tránh tình trạng nhóm hoàn thành nhiều ca kiểm thử nhưng vẫn chưa có bằng chứng cho một nhu cầu quan trọng.

## 2. Phạm vi: kiểm thử những gì và giới hạn ở đâu?

Phạm vi xác định phần sản phẩm, tình huống sử dụng và thuộc tính chất lượng sẽ được kiểm thử trong một đợt hoặc một giai đoạn. Phạm vi cũng cần nêu rõ những phần chưa kiểm thử, để các bên liên quan hiểu giới hạn của kết luận.

Khi xác định phạm vi, hãy xem xét các chiều sau:

| Chiều phạm vi | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Chức năng và luồng nghiệp vụ | Tính năng hoặc hành trình nào cần được xác nhận? | Tạo giỏ hàng, áp dụng mã giảm giá, thanh toán, hủy đơn |
| Người dùng và quyền hạn | Những vai trò nào sẽ sử dụng hệ thống? | Khách vãng lai, khách đã đăng nhập, nhân viên vận hành |
| Tích hợp | Hệ thống trao đổi dữ liệu với dịch vụ nào? | Cổng thanh toán, dịch vụ vận chuyển, email |
| Nền tảng và môi trường | Sản phẩm cần hoạt động trên môi trường nào? | Trình duyệt được hỗ trợ, thiết bị di động, môi trường staging |
| Mức kiểm thử | Cần kiểm tra ở cấp độ nào? | Thành phần, tích hợp, hệ thống, chấp nhận |
| Thuộc tính chất lượng | Ngoài tính đúng chức năng, cần đánh giá điều gì? | Hiệu năng, bảo mật, khả năng truy cập, tính tương thích |

Hãy ghi phạm vi thành ba nhóm rõ ràng:

1. **Trong phạm vi:** Các chức năng, luồng, nền tảng và thuộc tính sẽ được kiểm thử.
2. **Ngoài phạm vi:** Các phần được chủ động loại trừ trong đợt hiện tại, kèm lý do nếu việc loại trừ ảnh hưởng đến quyết định phát hành.
3. **Giả định và phụ thuộc:** Điều kiện cần có để kiểm thử diễn ra, chẳng hạn API của đối tác sẵn sàng, dữ liệu thử nghiệm đã được cấp hoặc môi trường có cấu hình tương đương sản xuất.

Không nên xác định phạm vi chỉ bằng danh sách màn hình hoặc chức năng. Một luồng nghiệp vụ thường đi qua nhiều thành phần; ví dụ thanh toán có thể liên quan đến giỏ hàng, tính thuế, mã giảm giá, cổng thanh toán, kho hàng và thông báo. Kiểm thử từng màn hình riêng lẻ không chứng minh được toàn bộ luồng hoạt động nhất quán.

Khi thời gian có hạn, ưu tiên phạm vi theo rủi ro. Có thể đánh giá từng tình huống dựa trên **mức độ ảnh hưởng nếu xảy ra lỗi** và **khả năng lỗi xuất hiện**. Thang điểm đơn giản từ 1 đến 5 cho mỗi yếu tố có thể giúp nhóm so sánh và thảo luận; điểm số chỉ hỗ trợ ra quyết định, không thay thế đánh giá chuyên môn. Những luồng quan trọng, dữ liệu nhạy cảm, tích hợp phức tạp và thay đổi gần đây thường cần được chú ý nhiều hơn.

## 3. Phương pháp: thu thập bằng chứng bằng cách nào?

Phương pháp mô tả cách nhóm thiết kế, chuẩn bị, thực hiện và đánh giá kiểm thử. Phương pháp phải phù hợp với mục tiêu và phạm vi đã chọn; không phải dự án nào cũng cần cùng một bộ kỹ thuật.

### 3.1. Chọn mức kiểm thử phù hợp

| Mức kiểm thử | Trọng tâm | Bằng chứng thường thu được |
|---|---|---|
| Kiểm thử thành phần (unit/component) | Logic hoặc thành phần riêng lẻ | Hàm xử lý, quy tắc tính toán và nhánh điều kiện hoạt động đúng |
| Kiểm thử tích hợp (integration) | Giao tiếp giữa các thành phần hoặc dịch vụ | Dữ liệu, giao thức, lỗi và trạng thái được trao đổi chính xác |
| Kiểm thử hệ thống (system) | Hành vi của sản phẩm như một hệ thống hoàn chỉnh | Luồng đầu cuối và các yêu cầu cấp hệ thống được đáp ứng |
| Kiểm thử chấp nhận (acceptance) | Mức độ phù hợp với nhu cầu và quy trình của người dùng hoặc bên nghiệp vụ | Người dùng mục tiêu có thể hoàn thành công việc trong điều kiện dự kiến |

Các mức này bổ sung cho nhau. Kiểm thử thành phần giúp phát hiện lỗi sớm và khoanh vùng nguyên nhân; kiểm thử tích hợp phát hiện sai lệch ở ranh giới; kiểm thử hệ thống xác nhận hành vi tổng thể; kiểm thử chấp nhận đánh giá sản phẩm trong bối cảnh sử dụng. Không nên dùng kết quả ở một mức để thay thế hoàn toàn bằng chứng ở mức khác.

### 3.2. Chọn loại kiểm thử theo rủi ro và mục tiêu

Tùy sản phẩm, chiến lược có thể kết hợp:

- **Kiểm thử chức năng:** Xác nhận hệ thống thực hiện đúng quy tắc và hành vi nghiệp vụ.
- **Kiểm thử hồi quy:** Kiểm tra các hành vi đã hoạt động trước đó sau khi có thay đổi.
- **Kiểm thử hiệu năng:** Đánh giá thời gian phản hồi, thông lượng và khả năng chịu tải trong điều kiện xác định.
- **Kiểm thử bảo mật:** Tìm điểm yếu trong xác thực, phân quyền, xử lý dữ liệu và các bề mặt tấn công liên quan.
- **Kiểm thử khả năng sử dụng và khả năng truy cập:** Đánh giá liệu người dùng mục tiêu, kể cả người dùng có nhu cầu tiếp cận khác nhau, có thể sử dụng sản phẩm hiệu quả hay không.
- **Kiểm thử tương thích và độ tin cậy:** Kiểm tra hành vi trên nền tảng được hỗ trợ và khả năng duy trì hoạt động trong các điều kiện dự kiến.
- **Kiểm thử thăm dò (exploratory):** Người kiểm thử vừa tìm hiểu sản phẩm, vừa thiết kế và thực hiện thử nghiệm để phát hiện vấn đề khó dự đoán bằng kịch bản cố định.

Không cần áp dụng tất cả loại kiểm thử cho mọi tính năng. Ví dụ, thay đổi giao diện nội dung tĩnh có thể cần kiểm tra hiển thị, khả năng truy cập và hồi quy giao diện; thay đổi luồng thanh toán cần chú trọng tính đúng đắn giao dịch, bảo mật, xử lý lỗi và tích hợp.

### 3.3. Chọn kỹ thuật thiết kế kiểm thử

Một số kỹ thuật giúp tạo bộ kiểm thử có hệ thống:

- **Phân vùng tương đương:** Chia đầu vào thành các nhóm được kỳ vọng xử lý tương tự, sau đó chọn đại diện từ mỗi nhóm.
- **Phân tích giá trị biên:** Tập trung vào giá trị ngay tại, ngay dưới và ngay trên giới hạn, vì lỗi thường xuất hiện ở ranh giới.
- **Bảng quyết định:** Liệt kê tổ hợp điều kiện và kết quả tương ứng, hữu ích với quy tắc nghiệp vụ có nhiều nhánh.
- **Chuyển trạng thái:** Kiểm tra các trạng thái hợp lệ, chuyển đổi hợp lệ và chuyển đổi bị cấm, chẳng hạn đơn hàng từ “chờ thanh toán” sang “đã thanh toán”.
- **Kiểm thử theo cặp (pairwise):** Chọn tập tổ hợp để bao phủ các cặp giá trị cấu hình khi có nhiều tham số và không thể kiểm tra mọi tổ hợp.
- **Kiểm thử dựa trên phiên và thăm dò:** Dùng hiểu biết của người kiểm thử để điều tra khu vực rủi ro, hành vi bất thường và các tình huống chưa được mô tả đầy đủ.

Kết quả thiết kế nên được liên kết với yêu cầu, rủi ro hoặc hành trình người dùng tương ứng. Liên kết này giúp nhóm biết yêu cầu nào đã có bằng chứng, yêu cầu nào còn thiếu và tác động của một thay đổi đến bộ kiểm thử.

### 3.4. Xác định cách thực thi và tự động hóa

Chiến lược cần quy định cách kết hợp kiểm thử thủ công và tự động. Tự động hóa phù hợp với kiểm thử lặp lại, có kết quả xác định và mang lại giá trị thường xuyên, chẳng hạn kiểm tra API, quy tắc tính toán, luồng hồi quy cốt lõi hoặc kiểm tra nhanh sau mỗi lần tích hợp. Kiểm thử thủ công có lợi thế khi cần quan sát trải nghiệm, khám phá hành vi mới hoặc đánh giá những tình huống khó mô tả thành quy tắc.

Không nên đặt mục tiêu tự động hóa toàn bộ ca kiểm thử bằng mọi giá. Chi phí xây dựng, bảo trì, dữ liệu, độ ổn định của môi trường và thời gian xử lý kết quả đều cần được tính đến. Một kiểm thử tự động thường xuyên thất bại do môi trường không ổn định có thể làm giảm niềm tin vào toàn bộ tín hiệu kiểm thử.

Quy trình thực thi thường gồm chuẩn bị môi trường và dữ liệu, chạy kiểm thử, ghi nhận bằng chứng, báo cáo lỗi, sửa lỗi, kiểm thử xác nhận bản sửa và chạy hồi quy phù hợp. Với lỗi quan trọng, cần ghi rõ bước tái hiện, kết quả mong đợi, kết quả thực tế, môi trường, dữ liệu liên quan và mức độ ảnh hưởng.

## 4. Nguồn lực: cần những gì để thực hiện chiến lược?

Nguồn lực không chỉ là số lượng người kiểm thử. Một chiến lược khả thi phải tính đến con người, kỹ năng, thời gian, môi trường, công cụ, dữ liệu và sự hỗ trợ từ các bên liên quan.

| Nhóm nguồn lực | Nội dung cần chuẩn bị | Ví dụ |
|---|---|---|
| Con người và kỹ năng | Vai trò, trách nhiệm, kiến thức nghiệp vụ và kỹ thuật | QA, lập trình viên, chủ sản phẩm, chuyên gia bảo mật, người dùng đại diện |
| Thời gian và năng lực | Lịch kiểm thử, thời lượng sửa lỗi, kiểm thử lại và dự phòng | Thời gian chuẩn bị dữ liệu, chạy hồi quy và kiểm thử chấp nhận |
| Môi trường | Cấu hình, dịch vụ phụ thuộc, quyền truy cập và khả năng làm mới | Staging có cấu hình gần với sản xuất, sandbox của cổng thanh toán |
| Công cụ | Quản lý ca kiểm thử, theo dõi lỗi, tự động hóa và quan sát hệ thống | Công cụ quản lý test, pipeline CI, log, metric và tracing |
| Dữ liệu kiểm thử | Dữ liệu đại diện, dữ liệu biên, dữ liệu lỗi và quy tắc bảo vệ dữ liệu | Đơn hàng thử, tài khoản theo vai trò, giao dịch sandbox |
| Hỗ trợ bên ngoài | Đầu mối và cam kết từ nhóm hoặc nhà cung cấp phụ thuộc | Nhóm vận hành, nhà cung cấp thanh toán, nhóm dữ liệu |

Phân công trách nhiệm phải rõ ràng. Người kiểm thử có thể thiết kế và thực hiện ca kiểm thử; lập trình viên hỗ trợ kiểm tra thành phần, phân tích nguyên nhân và sửa lỗi; chủ sản phẩm xác nhận quy tắc nghiệp vụ và chấp nhận rủi ro; nhóm vận hành chuẩn bị môi trường và khả năng quan sát; người dùng đại diện đánh giá luồng công việc thực tế. Một người có thể đảm nhiệm nhiều vai trò trong nhóm nhỏ, nhưng trách nhiệm ra quyết định vẫn cần được xác định.

Dữ liệu và môi trường thường là điểm nghẽn bị đánh giá thấp. Nếu môi trường không phản ánh các tích hợp quan trọng hoặc dữ liệu không bao phủ tình huống thực tế, kết quả có thể tạo cảm giác an toàn sai lệch. Dữ liệu nhạy cảm cần được che giấu hoặc thay thế theo quy định của tổ chức; không đưa dữ liệu cá nhân hoặc bí mật sản xuất vào môi trường thử nghiệm nếu chưa được cho phép và bảo vệ phù hợp.

Hãy kiểm tra tính khả thi trước khi cam kết phạm vi. Nếu không có thiết bị, tài khoản, chuyên môn hoặc dịch vụ phụ thuộc cần thiết, nhóm phải điều chỉnh kế hoạch, tìm nguồn lực bổ sung hoặc ghi rõ rủi ro còn lại.

## 5. Tiêu chí: khi nào có thể kết luận kiểm thử đạt yêu cầu?

Tiêu chí biến mục tiêu chất lượng thành điều kiện có thể đánh giá. Nếu tiêu chí mơ hồ như “kiểm thử ổn” hoặc “không còn lỗi nghiêm trọng”, các bên có thể hiểu khác nhau và đưa ra quyết định thiếu nhất quán.

Nên xác định ít nhất ba nhóm tiêu chí:

1. **Tiêu chí bắt đầu (entry criteria):** Điều kiện tối thiểu trước khi bắt đầu một giai đoạn kiểm thử. Ví dụ: yêu cầu và phạm vi đã được thống nhất, bản dựng đã triển khai, môi trường sẵn sàng, dữ liệu và tài khoản cần thiết đã có.
2. **Tiêu chí kết thúc (exit criteria):** Điều kiện để kết thúc giai đoạn kiểm thử. Ví dụ: các kịch bản ưu tiên cao đã chạy, luồng quan trọng đạt kết quả mong đợi, lỗi còn mở đã được phân loại và rủi ro tồn dư được ghi nhận.
3. **Tiêu chí chấp nhận (acceptance criteria):** Điều kiện để bên có thẩm quyền xác nhận sản phẩm hoặc tính năng đáp ứng nhu cầu đã thống nhất. Ví dụ: người dùng mục tiêu hoàn thành được hành trình nghiệp vụ, kết quả dữ liệu chính xác và các yêu cầu chất lượng bắt buộc được đáp ứng.

Tiêu chí nên đo được và gắn với bằng chứng. Các chỉ số có thể gồm:

- Tỷ lệ yêu cầu hoặc rủi ro quan trọng có ca kiểm thử và bằng chứng tương ứng.
- Kết quả đạt, không đạt, bị chặn và chưa thực hiện của các kịch bản theo mức ưu tiên.
- Số lỗi còn mở theo mức độ nghiêm trọng, tác động và trạng thái xử lý.
- Kết quả đo hiệu năng so với ngưỡng đã thống nhất, trong điều kiện tải và môi trường được mô tả.
- Kết quả đánh giá bảo mật, khả năng truy cập hoặc tương thích theo yêu cầu áp dụng.
- Rủi ro chưa được kiểm thử hoặc chưa được xử lý, cùng người chịu trách nhiệm chấp nhận rủi ro.

Ví dụ, một cổng thanh toán có thể đặt điều kiện kết thúc là tất cả kịch bản thanh toán thành công, thất bại, hủy và gửi lại yêu cầu ở mức ưu tiên cao đều đã chạy; không còn lỗi nghiêm trọng chưa có phương án xử lý được phê duyệt; giao dịch không bị ghi nhận trùng; và kết quả đối soát khớp với dữ liệu thử nghiệm. Ngưỡng cụ thể phải lấy từ yêu cầu sản phẩm, mức rủi ro và thỏa thuận của các bên, không áp dụng máy móc một con số chung cho mọi dự án.

Tiêu chí kết thúc kiểm thử không tự động đồng nghĩa với quyết định phát hành. Quyết định phát hành còn phụ thuộc vào mức rủi ro còn lại, tác động kinh doanh, kế hoạch khắc phục, khả năng giám sát và người có thẩm quyền chấp nhận rủi ro. Báo cáo cần nêu cả điều đã được xác nhận lẫn giới hạn của bằng chứng.

## 6. Kết nối năm thành phần thành một chiến lược thống nhất

Năm thành phần cần được trình bày trong cùng một mạch lập luận. Có thể dùng bảng sau để rà soát tính nhất quán:

| Thành phần | Câu hỏi trọng tâm | Đầu ra nên có |
|---|---|---|
| Mục tiêu | Cần chứng minh kết quả sử dụng hoặc thuộc tính nào? | Mục tiêu kiểm thử gắn với nhu cầu và rủi ro |
| Phạm vi | Phần nào được kiểm thử, phần nào bị loại trừ? | Danh sách trong/ngoài phạm vi, giả định và phụ thuộc |
| Phương pháp | Cần mức, loại và kỹ thuật kiểm thử nào? | Cách tiếp cận, thiết kế, thực thi và tự động hóa |
| Nguồn lực | Ai thực hiện và cần điều kiện gì? | Vai trò, năng lực, lịch, môi trường, công cụ và dữ liệu |
| Tiêu chí | Bằng chứng nào đủ để bắt đầu, kết thúc và chấp nhận? | Điều kiện đo được, ngưỡng chất lượng và quy tắc ra quyết định |

Ví dụ với luồng thanh toán trực tuyến:

1. **Mục tiêu:** Xác nhận khách hàng hoàn tất giao dịch chính xác, an toàn và nhận được trạng thái đơn hàng nhất quán.
2. **Phạm vi:** Bao gồm tạo đơn, áp dụng giảm giá, gọi cổng thanh toán, xử lý thành công/thất bại/hủy, cập nhật đơn hàng và gửi thông báo. Ghi rõ các phương thức thanh toán hoặc nền tảng chưa hỗ trợ.
3. **Phương pháp:** Kiểm thử thành phần cho quy tắc tính tiền; kiểm thử tích hợp với sandbox của cổng thanh toán; kiểm thử hệ thống cho luồng đầu cuối; kiểm thử thăm dò cho các tình huống mất kết nối, gửi lại yêu cầu và thao tác lặp; tự động hóa các trường hợp hồi quy ổn định.
4. **Nguồn lực:** QA, lập trình viên phụ trách thanh toán, chủ sản phẩm, tài khoản sandbox, dữ liệu đơn hàng thử, môi trường staging, log giao dịch và công cụ theo dõi lỗi.
5. **Tiêu chí:** Các tình huống ưu tiên cao có kết quả đạt; số tiền và trạng thái giao dịch chính xác; không tạo giao dịch hoặc đơn hàng trùng; lỗi nghiêm trọng được xử lý hoặc được người có thẩm quyền chấp nhận rõ ràng; bằng chứng và rủi ro còn lại được ghi trong báo cáo.

Ví dụ này cho thấy mỗi thành phần phải hỗ trợ cùng một kết quả. Nếu mục tiêu yêu cầu xác nhận tính nhất quán giao dịch nhưng phạm vi bỏ qua tích hợp thanh toán, hoặc phương pháp chỉ kiểm tra giao diện, chiến lược sẽ không tạo đủ bằng chứng. Nếu tiêu chí không đề cập giao dịch trùng, nhóm có thể hoàn thành kiểm thử mà vẫn bỏ sót rủi ro quan trọng.

## 7. Duy trì chiến lược khi sản phẩm thay đổi

Chiến lược kiểm thử không phải tài liệu viết một lần rồi giữ nguyên. Khi yêu cầu, kiến trúc, nhà cung cấp, nền tảng hoặc mức độ rủi ro thay đổi, nhóm cần xem xét lại cả năm thành phần. Một thay đổi ở dịch vụ thanh toán có thể làm thay đổi phạm vi tích hợp, phương pháp kiểm thử, dữ liệu cần chuẩn bị, chuyên môn cần huy động và tiêu chí chấp nhận.

Sau mỗi đợt kiểm thử, hãy đối chiếu mục tiêu với bằng chứng thu được, ghi nhận các khu vực chưa được bao phủ, phân tích lỗi thoát ra môi trường sử dụng và cập nhật ưu tiên cho chu kỳ tiếp theo. Dùng kết quả thực tế để điều chỉnh chiến lược, chẳng hạn bổ sung kiểm thử chuyển trạng thái nếu nhiều lỗi phát sinh khi đơn hàng đổi trạng thái hoặc tăng kiểm thử tương thích nếu lỗi tập trung ở một nền tảng cụ thể.

Các sai lầm thường gặp cần tránh gồm:

- Viết mục tiêu chung chung, không gắn với nhu cầu hoặc quyết định cần đưa ra.
- Mô tả phạm vi chỉ theo màn hình, bỏ qua luồng đầu cuối và tích hợp.
- Chọn kỹ thuật vì nhóm quen dùng, dù kỹ thuật đó không tạo bằng chứng cho rủi ro chính.
- Lập lịch mà không tính thời gian chuẩn bị môi trường, dữ liệu, sửa lỗi và kiểm thử lại.
- Đặt tiêu chí định tính hoặc thay đổi tiêu chí sau khi đã thấy kết quả mà không ghi nhận quyết định.
- Báo cáo tỷ lệ ca kiểm thử đạt như thể đó là bằng chứng đầy đủ về chất lượng, trong khi các yêu cầu quan trọng chưa được kiểm tra.

Một chiến lược tốt giúp các bên thống nhất kỳ vọng trước khi kiểm thử bắt đầu và hiểu đúng kết quả khi kiểm thử kết thúc. Khi mục tiêu rõ, phạm vi có ranh giới, phương pháp phù hợp, nguồn lực khả thi và tiêu chí đo được, nhóm có thể tập trung vào rủi ro quan trọng và đưa ra quyết định dựa trên bằng chứng.
