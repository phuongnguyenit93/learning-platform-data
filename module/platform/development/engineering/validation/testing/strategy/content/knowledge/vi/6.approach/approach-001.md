# Lựa chọn cách tiếp cận từ mục tiêu, rủi ro và bối cảnh thực tế

Trong chiến lược kiểm thử `VALIDATION_TESTING_STRATEGY`, cách tiếp cận kiểm thử (testing approach) mô tả những nguyên tắc và phương pháp mà nhóm lựa chọn để tạo đủ bằng chứng về chất lượng sản phẩm. Cách tiếp cận định hướng nhóm sẽ kiểm tra điều gì trước, dùng kỹ thuật nào, kiểm tra ở mức độ nào, tự động hóa phần nào và điều chỉnh ra sao khi sản phẩm hoặc bối cảnh thay đổi.

Không có một cách tiếp cận duy nhất phù hợp với mọi dự án. Một dịch vụ thanh toán cần chú trọng tính toàn vẹn giao dịch, bảo mật và khả năng phục hồi. Một ứng dụng nội bộ ít người dùng có thể ưu tiên quy tắc nghiệp vụ và khả năng sử dụng. Một hệ thống điều khiển thiết bị có thể cần kiểm tra thời gian thực, an toàn và tương tác phần cứng. Cách tiếp cận phù hợp phải bắt đầu từ mục tiêu, rủi ro và điều kiện thực tế của sản phẩm.

## 1. Cách tiếp cận kiểm thử là gì?

Cách tiếp cận kiểm thử là định hướng tổng thể cho việc lựa chọn và kết hợp hoạt động kiểm thử trong một sản phẩm, dự án hoặc đợt phát hành. Nó giúp trả lời các câu hỏi:

- Chúng ta cần tạo bằng chứng gì để ra quyết định về chất lượng?
- Rủi ro nào cần được giảm thiểu trước và vì sao?
- Những cấp độ, loại và kỹ thuật kiểm thử nào phù hợp với hệ thống?
- Hoạt động nào nên diễn ra sớm, liên tục, theo đợt hoặc sau khi phát hành?
- Phần nào có thể tự động hóa, phần nào cần phán đoán của con người?
- Nguồn lực, môi trường, dữ liệu và phụ thuộc nào cần có?
- Khi nào có đủ bằng chứng để tiếp tục, phát hành hoặc chấp nhận rủi ro còn lại?

Cách tiếp cận có thể kết hợp nhiều phương pháp. Ví dụ, nhóm có thể dùng cách tiếp cận dựa trên rủi ro để quyết định ưu tiên, dựa trên yêu cầu để bảo đảm truy vết, kiểm thử khám phá để tìm vấn đề chưa được dự đoán và tự động hóa hồi quy để kiểm tra thường xuyên.

### Phân biệt mục tiêu, chiến lược và cách tiếp cận

Các khái niệm này liên quan nhưng có vai trò khác nhau:

| Khái niệm | Câu hỏi chính | Ví dụ |
|---|---|---|
| Mục tiêu kiểm thử | Cần đạt điều gì hoặc hỗ trợ quyết định nào? | Xác nhận giao dịch không bị ghi nhận hai lần và cung cấp đủ bằng chứng cho phát hành |
| Chiến lược kiểm thử | Định hướng quản lý kiểm thử ở phạm vi sản phẩm hoặc tổ chức là gì? | Ưu tiên rủi ro, truy vết yêu cầu, kiểm thử nhiều lớp và theo dõi sau phát hành |
| Cách tiếp cận kiểm thử | Sẽ áp dụng nguyên tắc, phương pháp và kỹ thuật nào trong bối cảnh cụ thể? | Kiểm thử hợp đồng API, kiểm thử tích hợp, kiểm tra đồng thời, kiểm thử khám phá và giám sát giao dịch |
| Kế hoạch kiểm thử | Ai làm gì, khi nào, ở đâu và với nguồn lực nào? | Phân công người thực hiện, môi trường staging, dữ liệu, lịch chạy và đầu mối báo cáo |

Một chiến lược có thể giữ định hướng ổn định qua nhiều phiên bản, trong khi cách tiếp cận và kế hoạch được điều chỉnh theo từng thay đổi, rủi ro hoặc điều kiện triển khai.

## 2. Bắt đầu từ mục tiêu kiểm thử

Trước khi chọn phương pháp, nhóm cần làm rõ kết quả mà hoạt động kiểm thử phải hỗ trợ. Mục tiêu có thể khác nhau giữa các sản phẩm và giữa các giai đoạn:

- **Xác nhận chức năng:** chứng minh các luồng và quy tắc nghiệp vụ quan trọng hoạt động đúng.
- **Giảm rủi ro:** tìm lỗi có thể gây mất dữ liệu, sai giao dịch, lộ thông tin hoặc gián đoạn dịch vụ.
- **Đánh giá thuộc tính chất lượng:** thu thập bằng chứng về hiệu năng, độ tin cậy, khả năng sử dụng, tương thích, bảo mật hoặc khả năng tiếp cận.
- **Hỗ trợ quyết định phát hành:** xác định yêu cầu bắt buộc đã được kiểm tra, lỗi còn mở và rủi ro tồn dư.
- **Xác nhận nhu cầu sử dụng:** kiểm tra giải pháp có hỗ trợ người dùng hoàn thành công việc trong bối cảnh thực tế.
- **Duy trì chất lượng qua thay đổi:** phát hiện hồi quy khi mã nguồn, cấu hình, dữ liệu hoặc dịch vụ phụ thuộc thay đổi.

Mục tiêu nên được diễn đạt theo kết quả và bằng chứng, thay vì chỉ ghi “thực hiện đầy đủ kiểm thử”. Ví dụ, “kiểm tra mọi đường đi có thể làm ghi nhận thanh toán hai lần và chứng minh yêu cầu lặp không tạo giao dịch mới” xác định rõ vấn đề cần kiểm soát hơn là “test chức năng thanh toán”.

Một dự án có thể có nhiều mục tiêu. Hãy xác định mục tiêu nào là bắt buộc, mục tiêu nào hỗ trợ cải tiến và mục tiêu nào cần hoàn thành trước một quyết định cụ thể. Việc này giúp nhóm tránh tối ưu một chỉ số dễ đo trong khi bỏ sót kết quả quan trọng với người dùng.

## 3. Phân tích rủi ro để quyết định ưu tiên

Rủi ro sản phẩm phản ánh khả năng một vấn đề ảnh hưởng đến chất lượng và hậu quả khi vấn đề xảy ra. Khi lựa chọn cách tiếp cận, nhóm cần đánh giá cả khả năng xảy ra lẫn mức độ tác động.

Các tín hiệu làm tăng khả năng xảy ra có thể gồm:

- Thành phần mới, phức tạp hoặc vừa được thay đổi lớn.
- Logic có nhiều nhánh, trạng thái hoặc quy tắc phụ thuộc lẫn nhau.
- Công nghệ, thư viện hoặc dịch vụ tích hợp chưa quen thuộc.
- Lịch sử có nhiều lỗi, sự cố hoặc thay đổi gây hồi quy.
- Thiếu tài liệu, thiếu test tự động hoặc khó tạo môi trường đại diện.

Mức độ tác động cần xét đến:

- Tổn thất tài chính, sai lệch giao dịch hoặc mất dữ liệu.
- Ảnh hưởng đến an toàn, quyền riêng tư, bảo mật hoặc tuân thủ.
- Số lượng người dùng và mức gián đoạn công việc.
- Khả năng phát hiện, khôi phục và đảo ngược hậu quả.
- Ảnh hưởng đến uy tín, cam kết dịch vụ và hoạt động của đối tác.

### Chuyển rủi ro thành lựa chọn kiểm thử

| Đặc điểm rủi ro | Cách tiếp cận phù hợp | Bằng chứng nên tìm |
|---|---|---|
| Quy tắc nghiệp vụ phức tạp | Dựa trên yêu cầu, bảng quyết định, phân vùng tương đương và kiểm thử biên | Các tổ hợp đầu vào, điều kiện và kết quả được đối chiếu với quy tắc |
| Tích hợp nhiều dịch vụ | Kiểm thử hợp đồng, tích hợp, mô phỏng lỗi phụ thuộc và kiểm tra luồng xuyên suốt | Schema, trạng thái, retry, timeout, xử lý lỗi và tính nhất quán dữ liệu |
| Thay đổi thường xuyên | Hồi quy tự động theo rủi ro, kiểm tra khói và kiểm thử liên tục trong pipeline | Kết quả lặp lại theo từng thay đổi và cảnh báo hồi quy |
| Hành vi khó dự đoán | Kiểm thử khám phá, kiểm thử dựa trên kinh nghiệm và mô hình trạng thái | Lỗi bất ngờ, chuỗi thao tác gây lỗi và khoảng trống trong giả định |
| Hiệu năng dưới tải lớn | Kiểm thử tải, sức chịu đựng, tăng đột biến và phân tích tài nguyên | Độ trễ theo phân vị, thông lượng, tỷ lệ lỗi và mức sử dụng tài nguyên |
| Bảo mật và phân quyền | Phân tích mối đe dọa, kiểm thử quyền, rà soát cấu hình và kiểm thử bảo mật chuyên sâu | Bằng chứng truy cập hợp lệ/bất hợp lệ, lỗ hổng và khả năng kiểm toán |
| Trải nghiệm người dùng quan trọng | Kiểm thử khả năng sử dụng, khả năng tiếp cận và xác nhận với người dùng đại diện | Tỷ lệ hoàn thành tác vụ, lỗi thao tác, thời gian và trở ngại quan sát được |

Rủi ro cao thường cần nhiều lớp bằng chứng, kiểm tra sớm và người có chuyên môn phù hợp. Rủi ro thấp hơn có thể dùng kiểm tra đại diện hoặc lấy mẫu, nhưng vẫn cần duy trì các kiểm tra nền tảng và nghĩa vụ bắt buộc. Không nên dùng một điểm rủi ro tổng hợp để bỏ qua yêu cầu an toàn, bảo mật hoặc tuân thủ có tính bắt buộc.

## 4. Xem xét bối cảnh thực tế của sản phẩm

Hai sản phẩm có cùng chức năng vẫn có thể cần cách tiếp cận khác nhau vì môi trường, kiến trúc, người dùng và giới hạn triển khai khác nhau. Trước khi quyết định, nhóm nên xem xét các khía cạnh sau.

### Vòng đời phát triển và nhịp phát hành

Trong môi trường phát hành thường xuyên, kiểm thử cần tích hợp vào quy trình phát triển để phản hồi nhanh. Các kiểm tra đơn vị, hợp đồng, tích hợp và hồi quy ngắn có thể chạy tự động ở mỗi thay đổi; kiểm thử chuyên sâu hoặc xác nhận với người dùng được bố trí theo mức rủi ro và mốc phát hành.

Với dự án có các giai đoạn và mốc phê duyệt rõ, nhóm có thể tổ chức review yêu cầu, review thiết kế, kiểm thử theo từng mức và kiểm thử chấp nhận theo các cổng đã định nghĩa. Dù mô hình phát triển khác nhau, việc xác nhận yêu cầu sớm và thu thập bằng chứng liên tục vẫn có ích.

### Kiến trúc và đặc tính kỹ thuật

Một ứng dụng nguyên khối có thể tập trung vào kiểm thử module, tích hợp nội bộ và luồng hệ thống. Hệ thống microservices cần chú ý hợp đồng API hoặc sự kiện, tương thích phiên bản, lỗi mạng, timeout, retry, tính nhất quán cuối cùng và khả năng quan sát xuyên dịch vụ. Ứng dụng di động cần xét thiết bị, hệ điều hành, kích thước màn hình, quyền hệ thống, mạng không ổn định và vòng đời ứng dụng.

Với hệ thống dữ liệu, cần quan tâm chất lượng dữ liệu đầu vào, biến đổi, tính toàn vẹn, tính lặp lại của pipeline và khả năng đối soát. Với hệ thống thời gian thực hoặc tích hợp phần cứng, độ trễ, thứ tự sự kiện, mất kết nối và hành vi khi thiết bị ở trạng thái bất thường có thể là trọng tâm.

### Người dùng và bối cảnh nghiệp vụ

Nhóm người dùng có kỹ năng, thiết bị và điều kiện làm việc khác nhau. Một thao tác dễ dàng với nhân viên văn phòng có thể khó thực hiện với nhân viên kho đang dùng găng tay hoặc kết nối mạng chập chờn. Hãy lựa chọn nhóm người tham gia, kịch bản và môi trường thử nghiệm phản ánh đúng bối cảnh sử dụng dự kiến.

### Quy định, hợp đồng và chính sách

Nếu sản phẩm chịu yêu cầu pháp lý, tiêu chuẩn ngành, hợp đồng dịch vụ hoặc chính sách nội bộ, các yêu cầu này cần được đưa vào test basis và điều kiện chấp nhận. Cách tiếp cận phải xác định được bằng chứng cần lưu, người có thẩm quyền xem xét và khả năng truy vết. Không thể loại bỏ một hoạt động bắt buộc chỉ vì nguồn lực hạn chế mà không xử lý theo quy trình có thẩm quyền.

### Nguồn lực và khả năng kiểm thử

Đánh giá số người, kỹ năng, thời gian, công cụ, môi trường, dữ liệu, chi phí và phụ thuộc. Xác định điều gì có thể tự động hóa tin cậy, điều gì cần chuyên gia hoặc người dùng tham gia, và điều gì chưa thể kiểm tra. Giới hạn cần được phản ánh thành rủi ro tồn dư và điều kiện quyết định.

## 5. Các cách tiếp cận phổ biến và khi nào nên dùng

Các cách tiếp cận dưới đây có thể được kết hợp. Nhóm nên chọn theo câu hỏi cần trả lời thay vì áp dụng máy móc tên gọi.

### Dựa trên yêu cầu (requirements-based)

Thiết kế test từ yêu cầu, user story, tiêu chí chấp nhận và quy tắc nghiệp vụ. Mỗi yêu cầu được liên kết với một hoặc nhiều trường hợp kiểm thử và kết quả.

Phù hợp khi yêu cầu rõ, cần chứng minh mức bao phủ, có cam kết với khách hàng hoặc cần truy vết cho kiểm toán. Cần bổ sung review yêu cầu vì test chỉ dựa trên đặc tả có thể bỏ sót nhu cầu chưa được ghi nhận hoặc đặc tả sai.

### Dựa trên rủi ro (risk-based)

Ưu tiên phạm vi, độ sâu và thứ tự kiểm thử theo khả năng xảy ra và mức độ tác động của lỗi. Rủi ro được xem xét lại khi thay đổi, sự cố hoặc thông tin mới xuất hiện.

Phù hợp khi thời gian và nguồn lực có giới hạn, hệ thống có nhiều khu vực với mức ảnh hưởng khác nhau hoặc cần giải thích cơ sở cho quyết định phát hành. Phương pháp này đòi hỏi nhóm có sự hiểu biết về nghiệp vụ và rủi ro; đánh giá hời hợt có thể dẫn đến ưu tiên sai.

### Dựa trên mô hình (model-based)

Xây dựng mô hình biểu diễn trạng thái, luồng, quy tắc hoặc quan hệ đầu vào/đầu ra, rồi tạo hoặc chọn test để bao phủ mô hình. Ví dụ, một đơn hàng có thể đi qua các trạng thái tạo mới, chờ thanh toán, đã thanh toán, hủy và hoàn tiền.

Phù hợp với hệ thống có nhiều trạng thái, quy trình phức tạp, giao thức hoặc quy tắc chuyển trạng thái. Mô hình cần phản ánh đúng nghiệp vụ và được duy trì khi sản phẩm thay đổi; mô hình sai sẽ tạo ra test có vẻ đầy đủ nhưng kiểm tra sai hành vi.

### Kiểm thử khám phá (exploratory)

Người kiểm thử vừa học hệ thống, thiết kế thử nghiệm và thực hiện kiểm tra, sử dụng kết quả quan sát để định hướng bước tiếp theo. Có thể đặt phiên khám phá theo mục tiêu, thời lượng và rủi ro cụ thể.

Phù hợp khi tính năng mới, yêu cầu chưa đầy đủ, hành vi phức tạp hoặc nhóm cần tìm lỗi ngoài các kịch bản đã dự đoán. Nên ghi lại mục tiêu, dữ liệu, đường đi, phát hiện và câu hỏi còn mở để kết quả có thể chia sẻ và theo dõi.

### Dựa trên kinh nghiệm và checklist

Sử dụng hiểu biết của tester, lỗi lịch sử, mẫu lỗi phổ biến, checklist và heuristic để chọn trường hợp có khả năng tìm ra vấn đề. Ví dụ, kiểm tra quyền, giá trị rỗng, dữ liệu rất dài, ký tự đặc biệt, múi giờ, gửi lặp và mất kết nối.

Phù hợp để bổ sung cho cách tiếp cận dựa trên yêu cầu, đặc biệt khi đặc tả chưa bao quát mọi tình huống. Checklist cần được cập nhật theo lỗi thực tế và không nên thay thế phân tích yêu cầu hoặc kiểm tra rủi ro có hệ thống.

### Dựa trên tuân thủ (compliance-based)

Xác định các nghĩa vụ từ quy định, tiêu chuẩn, hợp đồng hoặc chính sách rồi lập bằng chứng chứng minh đáp ứng. Bằng chứng có thể gồm review, test, log, báo cáo đánh giá, hồ sơ phê duyệt và truy vết.

Phù hợp với sản phẩm chịu kiểm toán hoặc nghĩa vụ bắt buộc. Cần xác định phiên bản quy định, phạm vi áp dụng, cách diễn giải và người có thẩm quyền; không nên chỉ đánh dấu checklist mà thiếu bằng chứng thực tế.

### Kiểm thử liên tục (continuous testing)

Tích hợp các kiểm tra tự động và phản hồi chất lượng vào pipeline phát triển, từ commit, build, triển khai thử đến theo dõi sau phát hành. Mục tiêu là phát hiện vấn đề sớm và cung cấp tín hiệu đủ nhanh cho nhóm.

Phù hợp với sản phẩm phát hành thường xuyên, có pipeline và môi trường tự động hóa đáng tin cậy. Cần kiểm soát độ ổn định của test, thời gian pipeline, dữ liệu, bí mật truy cập và cách xử lý test thất bại. Không phải mọi hoạt động, như đánh giá khả năng sử dụng hoặc kiểm thử khám phá sâu, đều có thể thay thế bằng pipeline.

## 6. Kết hợp các phương pháp thành một cách tiếp cận nhất quán

Trong thực tế, một phương pháp đơn lẻ hiếm khi đủ. Ví dụ, cách tiếp cận dựa trên yêu cầu giúp chứng minh từng tiêu chí đã ghi; cách tiếp cận dựa trên rủi ro quyết định phần nào cần kiểm tra sâu; kiểm thử khám phá tìm các tình huống chưa được mô tả; kiểm thử liên tục duy trì phản hồi nhanh sau mỗi thay đổi.

Một mô hình kết hợp có thể gồm:

1. **Trước khi phát triển:** xác nhận nhu cầu, review yêu cầu, phân tích rủi ro, xác định tiêu chí chất lượng và khả năng kiểm thử.
2. **Trong khi phát triển:** review thiết kế và mã nguồn, kiểm thử đơn vị, kiểm tra hợp đồng, phân tích tĩnh và kiểm tra bảo mật phù hợp.
3. **Khi tích hợp:** kiểm thử tích hợp, dữ liệu, giao tiếp dịch vụ, lỗi phụ thuộc, retry, timeout và các trạng thái liên quan.
4. **Trước phát hành:** kiểm thử hệ thống, hồi quy theo rủi ro, hiệu năng, bảo mật, khả năng sử dụng và kiểm thử chấp nhận.
5. **Sau phát hành:** theo dõi chỉ số, log, trace, phản hồi người dùng, sự cố và hành vi thực tế để điều chỉnh cách tiếp cận.

Đây là một gợi ý tổ chức, không phải chuỗi giai đoạn cứng. Với phát triển liên tục, nhiều hoạt động diễn ra lặp lại ở mỗi thay đổi; với hệ thống có yêu cầu phê duyệt, một số bằng chứng cần được tập hợp tại các mốc chính thức.

### Chọn mức kiểm thử theo ranh giới thành phần

Nên kiểm tra một hành vi ở nơi có thể quan sát và cô lập lỗi với chi phí hợp lý. Quy tắc nghiệp vụ thuần túy thường phù hợp với kiểm thử đơn vị. Hợp đồng giữa dịch vụ phù hợp với kiểm thử hợp đồng hoặc tích hợp. Luồng người dùng xuyên suốt cần kiểm thử hệ thống hoặc chấp nhận. Không nên đẩy mọi kiểm tra lên giao diện đầu cuối vì các test này thường chậm, khó chẩn đoán và dễ bị ảnh hưởng bởi môi trường; cũng không nên chỉ kiểm tra đơn vị nếu rủi ro nằm ở tích hợp và vận hành.

### Quyết định tự động hóa

Tự động hóa có giá trị khi kiểm tra được lặp lại thường xuyên, có kết quả xác định, dữ liệu và môi trường có thể kiểm soát, đồng thời chi phí bảo trì hợp lý. Các ứng viên thường gặp gồm kiểm thử đơn vị, API, hợp đồng, hồi quy ổn định, kiểm tra cấu hình và một số luồng khói.

Kiểm thử khám phá, phỏng vấn, đánh giá trải nghiệm hoặc xác nhận nghiệp vụ còn phụ thuộc nhiều vào quan sát và phán đoán. Có thể dùng công cụ hỗ trợ ghi nhận và phân tích, nhưng không nên coi việc tự động hóa thao tác là thay thế hoàn toàn đánh giá của con người.

Khi quyết định tự động hóa, hãy cân nhắc:

- Tần suất chạy và số lần thực hiện dự kiến.
- Độ ổn định của yêu cầu và giao diện được kiểm tra.
- Khả năng tạo, làm sạch và tái lập dữ liệu.
- Chi phí phát triển, chạy, điều tra lỗi giả và bảo trì.
- Giá trị của phản hồi nhanh so với kiểm tra thủ công hoặc khám phá.

## 7. Xây dựng cách tiếp cận theo từng bước

Một quy trình lựa chọn thực tế có thể triển khai như sau:

### Bước 1: Xác định quyết định cần hỗ trợ

Nêu rõ nhóm đang kiểm thử cho mục tiêu nào: chấp nhận một tính năng, đánh giá bản phát hành, giảm rủi ro bảo mật, kiểm tra hiệu năng hay xác nhận quy trình với người dùng. Ghi rõ ai sử dụng kết quả và họ cần bằng chứng gì để quyết định.

### Bước 2: Thu thập test basis và hiểu hệ thống

Đọc yêu cầu, kiến trúc, luồng nghiệp vụ, giao diện, hợp đồng tích hợp, dữ liệu và lịch sử sự cố. Làm rõ các điểm mơ hồ, giả định, thành phần phụ thuộc và phạm vi hỗ trợ.

### Bước 3: Đánh giá rủi ro

Xác định vùng có khả năng lỗi, mức độ tác động và nghĩa vụ bắt buộc. Xếp thứ tự ưu tiên, ghi rõ lý do và điều chỉnh khi có thông tin mới.

### Bước 4: Chọn phương pháp và mức kiểm thử

Kết hợp kỹ thuật dựa trên yêu cầu, rủi ro, mô hình, khám phá, kinh nghiệm hoặc tuân thủ theo đặc tính từng khu vực. Xác định nơi cần review, kiểm thử đơn vị, hợp đồng, tích hợp, hệ thống, chấp nhận, phi chức năng và kiểm tra sau phát hành.

### Bước 5: Đánh giá tính khả thi

Xác nhận kỹ năng, số người, lịch, công cụ, môi trường, dữ liệu và phụ thuộc. Nếu không đủ điều kiện, điều chỉnh thứ tự, bổ sung nguồn lực, chia phạm vi hoặc ghi nhận rủi ro tồn dư để xin quyết định.

### Bước 6: Xác định tiêu chí và bằng chứng

Với mỗi mục tiêu, ghi cách đo, điều kiện, ngưỡng, kết quả cần lưu, tiêu chí hoàn tất và người xem xét. Quy định cách xử lý khi test thất bại, không thể chạy hoặc kết quả không đủ tin cậy.

### Bước 7: Thử nghiệm cách tiếp cận và điều chỉnh

Chạy một nhóm kiểm tra đại diện để đánh giá thời gian phản hồi, độ ổn định, chất lượng dữ liệu và khả năng phát hiện lỗi. Nếu pipeline quá chậm, test không đáng tin cậy hoặc môi trường không đại diện, cần sửa cách tổ chức trước khi nhân rộng.

### Bước 8: Xem xét lại theo thay đổi và bằng chứng mới

Sau mỗi thay đổi lớn, sự cố hoặc phát hiện rủi ro mới, đánh giá xem ưu tiên, phạm vi, dữ liệu, kỹ thuật và nguồn lực còn phù hợp không. Cách tiếp cận là một quyết định có thể điều chỉnh, không phải tài liệu cố định từ đầu dự án.

## 8. Ví dụ xuyên suốt: nền tảng đặt hàng và quản lý tồn kho

Giả sử một nền tảng cho phép khách hàng đặt hàng trực tuyến, thanh toán qua cổng bên ngoài và cập nhật tồn kho qua một dịch vụ riêng. Mục tiêu là bảo đảm đơn hàng chính xác, không ghi nhận thanh toán hoặc trừ tồn kho trùng, đồng thời hỗ trợ phát hành thường xuyên.

### Bối cảnh và rủi ro

- API đặt hàng và dịch vụ tồn kho được phát triển bởi hai nhóm khác nhau.
- Cổng thanh toán có thể phản hồi chậm hoặc gửi webhook lặp.
- Khách hàng có thể tải lại trang hoặc gửi lại yêu cầu khi mạng gián đoạn.
- Nhóm phát hành hàng tuần, có pipeline CI và môi trường staging.
- Giao dịch sai có tác động tài chính và vận hành cao.

### Cách tiếp cận được lựa chọn

| Khu vực | Phương pháp | Lý do và bằng chứng |
|---|---|---|
| Tính giá và giảm giá | Dựa trên yêu cầu, bảng quyết định, test đơn vị và kiểm tra biên | Nhiều quy tắc kết hợp; cần chứng minh công thức và các trường hợp biên |
| Giao tiếp API giữa đặt hàng và tồn kho | Kiểm thử hợp đồng và tích hợp | Hai nhóm phát triển độc lập; cần xác nhận schema, phiên bản và xử lý lỗi |
| Thanh toán và webhook | Kiểm thử mô hình trạng thái, gửi lặp, timeout và kiểm tra đồng thời | Rủi ro ghi nhận thanh toán trùng hoặc sai trạng thái |
| Luồng mua hàng | Kiểm thử hệ thống và xác nhận với người dùng đại diện | Cần xác nhận toàn bộ hành trình và khả năng hiểu trạng thái đơn |
| Thay đổi thường xuyên | Hồi quy tự động trong CI theo rủi ro | Cần phản hồi nhanh sau mỗi lần tích hợp |
| Vận hành thực tế | Giám sát lỗi giao dịch, độ trễ, tồn kho và webhook sau phát hành | Một số vấn đề chỉ xuất hiện dưới tải và điều kiện mạng thực tế |

Nhóm không dựa vào một bộ test đầu cuối duy nhất. Các quy tắc tính giá được kiểm tra ở mức đơn vị; hợp đồng dịch vụ được kiểm tra độc lập; luồng giao dịch được kiểm tra xuyên suốt; và hành vi thực tế được theo dõi sau phát hành. Cách phân lớp này giúp lỗi được phát hiện gần nơi phát sinh và vẫn có bằng chứng cho các rủi ro xuyên hệ thống.

### Điều chỉnh khi bối cảnh thay đổi

Nếu cổng thanh toán thay đổi phiên bản webhook, nhóm cần tăng cường kiểm thử hợp đồng, tương thích ngược và các trạng thái giao dịch. Nếu xuất hiện sự cố tạo đơn trùng, cần xem lại idempotency, retry, xử lý đồng thời và dữ liệu lịch sử; đồng thời bổ sung hồi quy tự động cho lỗi đã phát hiện. Nếu số lượng đơn tăng đột biến, cần bổ sung kiểm thử tải và sức chịu đựng theo mô hình lưu lượng mới.

## 9. Đánh giá hiệu quả của cách tiếp cận

Không nên đánh giá cách tiếp cận chỉ bằng số lượng test hoặc tỷ lệ pass. Cần xem liệu phương pháp đã tạo ra bằng chứng hữu ích và giảm được rủi ro quan trọng hay chưa.

Một số tín hiệu có thể theo dõi:

- Tỷ lệ yêu cầu quan trọng có bằng chứng và liên kết truy vết.
- Mức bao phủ các rủi ro cao và các tình huống lỗi quan trọng.
- Lỗi nghiêm trọng được phát hiện trước phát hành so với sau phát hành.
- Thời gian từ khi thay đổi đến khi nhận được phản hồi kiểm thử.
- Tỷ lệ test tự động ổn định, thời gian chạy pipeline và số lần phải chạy lại do lỗi môi trường.
- Số lỗi lọt ra production, mức độ ảnh hưởng và thời gian phát hiện/khôi phục.
- Mức độ hoàn thành tác vụ và phản hồi của người dùng trong các kịch bản quan trọng.

Các chỉ số cần được đọc cùng bối cảnh. Số lỗi phát hiện giảm có thể là tín hiệu tốt, nhưng cũng có thể do kiểm thử thiếu chiều sâu. Tỷ lệ pass cao có thể phản ánh bộ test ổn định, hoặc phản ánh test chỉ kiểm tra luồng dễ. Hãy kết hợp số liệu với review chất lượng test, phân tích sự cố và phản hồi từ người dùng.

## 10. Những sai lầm thường gặp

**Chọn cách tiếp cận theo thói quen.** Dùng lại bộ test của dự án trước mà không xem xét kiến trúc, rủi ro và người dùng có thể bỏ sót vấn đề mới. Hãy dùng kinh nghiệm làm đầu vào, sau đó xác nhận lại theo bối cảnh hiện tại.

**Chỉ dựa trên yêu cầu đã viết.** Đặc tả có thể thiếu hoặc sai so với nhu cầu. Kết hợp review, trao đổi nghiệp vụ, prototype và quan sát người dùng khi cần xác nhận vấn đề cần giải quyết.

**Chỉ dựa trên rủi ro mà bỏ truy vết.** Ưu tiên rủi ro giúp phân bổ nỗ lực nhưng vẫn cần bảo đảm các yêu cầu bắt buộc có bằng chứng hoặc có quyết định xử lý rõ ràng.

**Coi tự động hóa là toàn bộ chiến lược.** Tự động hóa hỗ trợ kiểm tra lặp lại và phản hồi nhanh; nó không thay thế hoàn toàn kiểm thử khám phá, đánh giá khả năng sử dụng, review yêu cầu hoặc xác nhận nghiệp vụ.

**Áp dụng một mức kiểm thử cho mọi thành phần.** Kiểm thử đầu cuối quá nhiều có thể làm pipeline chậm và khó chẩn đoán; chỉ kiểm thử đơn vị lại không phát hiện được lỗi tích hợp. Hãy chọn mức kiểm tra theo vị trí của logic và rủi ro.

**Không tính đến môi trường và dữ liệu.** Test có thể pass trong môi trường không đại diện hoặc dùng dữ liệu không phản ánh thực tế. Cần nêu rõ điều kiện và giới hạn của bằng chứng.

**Không thay đổi cách tiếp cận sau sự cố.** Một lỗi lọt production là dữ liệu để xem lại giả định, test basis, rủi ro và phương pháp. Nếu chỉ sửa lỗi mà không cập nhật cách tiếp cận, cùng một nhóm nguyên nhân có thể tái diễn.

**Đo hiệu quả bằng số lượng test.** Nhiều test không đồng nghĩa nhiều rủi ro đã được kiểm soát. Cần xem chất lượng bằng chứng, khả năng phát hiện lỗi quan trọng và kết quả đối với người dùng.

## 11. Checklist lựa chọn cách tiếp cận kiểm thử

Trước khi lựa chọn:

- [ ] Mục tiêu kiểm thử và quyết định cần hỗ trợ đã được xác định.
- [ ] Test basis, kiến trúc, luồng nghiệp vụ và phụ thuộc đã được xem xét.
- [ ] Rủi ro được đánh giá theo khả năng xảy ra, tác động và nghĩa vụ bắt buộc.
- [ ] Người dùng, môi trường sử dụng và thuộc tính chất lượng quan trọng đã được nhận diện.

Khi thiết kế cách tiếp cận:

- [ ] Phương pháp được chọn phù hợp với loại yêu cầu và đặc tính rủi ro.
- [ ] Có kết hợp phù hợp giữa kiểm thử dựa trên yêu cầu, rủi ro, mô hình, khám phá hoặc tuân thủ.
- [ ] Mức kiểm thử và ranh giới thành phần được lựa chọn để phát hiện lỗi với chi phí hợp lý.
- [ ] Quyết định tự động hóa dựa trên tần suất, độ ổn định, dữ liệu và chi phí bảo trì.
- [ ] Môi trường, dữ liệu, kỹ năng, công cụ, thời gian và phụ thuộc đã được xác nhận.
- [ ] Tiêu chí hoàn tất, bằng chứng và cách xử lý kết quả chưa đạt đã rõ ràng.

Trong và sau khi thực hiện:

- [ ] Cách tiếp cận được thử nghiệm trên một phạm vi đại diện và điều chỉnh theo kết quả.
- [ ] Rủi ro chưa được kiểm tra hoặc chưa giảm đủ được ghi nhận.
- [ ] Chỉ số hiệu quả được đọc cùng chất lượng bằng chứng và phản hồi thực tế.
- [ ] Sự cố, thay đổi kiến trúc và phản hồi người dùng được dùng để cập nhật cách tiếp cận.

## 12. Tự kiểm tra mức độ hiểu

**Tình huống 1:** Một ứng dụng phát hành mỗi ngày và có nhiều thay đổi nhỏ. Cách tiếp cận phù hợp có thể tích hợp kiểm tra đơn vị, hợp đồng, khói và hồi quy tự động vào pipeline, đồng thời giữ kiểm thử khám phá và xác nhận người dùng cho thay đổi có rủi ro hoặc ảnh hưởng trải nghiệm lớn.

**Tình huống 2:** Một quy trình phê duyệt có nhiều trạng thái và chuyển tiếp phụ thuộc vai trò. Kiểm thử dựa trên mô hình trạng thái kết hợp bảng quyết định có thể giúp bao phủ các chuyển tiếp hợp lệ và không hợp lệ. Kiểm thử quyền và kiểm tra dữ liệu sau mỗi chuyển tiếp bổ sung bằng chứng về rủi ro.

**Tình huống 3:** Một hệ thống có ít người dùng nhưng xử lý dữ liệu tài chính quan trọng. Số người dùng thấp không làm giảm mức độ nghiêm trọng của lỗi. Cách tiếp cận cần chú trọng tính toàn vẹn, phân quyền, đối soát, nhật ký và khả năng khôi phục.

**Tình huống 4:** Một bộ test đầu cuối chạy rất lâu và thường thất bại do môi trường. Nhóm nên xem lại ranh giới kiểm thử, chuyển kiểm tra logic xuống mức đơn vị/API/hợp đồng khi phù hợp, cải thiện dữ liệu và môi trường, đồng thời giữ một số kịch bản đầu cuối đại diện cho luồng trọng yếu.

Khi chọn cách tiếp cận, hãy tự hỏi: **mục tiêu cần bằng chứng gì, rủi ro nào có thể gây hậu quả lớn, và bối cảnh cho phép nhóm kiểm tra bằng cách nào?** Câu trả lời cần giải thích được vì sao phương pháp được chọn phù hợp và giới hạn nào vẫn còn.

## Kết luận

Cách tiếp cận kiểm thử cần được lựa chọn từ mục tiêu, rủi ro và bối cảnh thực tế của sản phẩm. Mục tiêu xác định bằng chứng cần có; rủi ro quyết định ưu tiên và chiều sâu; kiến trúc, người dùng, vòng đời, quy định và nguồn lực quyết định phương pháp khả thi. Kết hợp đúng các cách tiếp cận dựa trên yêu cầu, rủi ro, mô hình, khám phá, tuân thủ và kiểm thử liên tục giúp nhóm tạo bằng chứng phù hợp, phát hiện vấn đề đúng lúc và đưa ra quyết định chất lượng có cơ sở.
