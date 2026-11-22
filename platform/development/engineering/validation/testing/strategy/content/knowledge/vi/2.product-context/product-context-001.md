# Xác định người dùng, mục tiêu kinh doanh và hành trình quan trọng

Một chiến lược kiểm thử xác thực chỉ có ý nghĩa khi nó kiểm tra được sản phẩm có giải quyết đúng vấn đề của đúng người dùng và tạo ra kết quả mà doanh nghiệp cần hay không. Vì vậy, trước khi chọn phương pháp kiểm thử, viết kịch bản hay xác định phạm vi, nhóm cần hiểu bối cảnh sản phẩm: ai sử dụng sản phẩm, họ muốn hoàn thành việc gì, doanh nghiệp kỳ vọng kết quả nào và hành trình nào có ảnh hưởng lớn nhất đến kết quả đó.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, việc xác định bối cảnh sản phẩm tạo nền tảng để lựa chọn giả thuyết cần kiểm chứng, người tham gia phù hợp, tình huống đại diện và bằng chứng đủ tin cậy. Nếu bỏ qua bước này, nhóm dễ kiểm thử những chức năng dễ nhìn thấy nhưng ít giá trị, hoặc tối ưu một chỉ số mà không cải thiện trải nghiệm và kết quả kinh doanh.

## 1. Xác định ai là người dùng và họ cần đạt điều gì

### Phân biệt người dùng, khách hàng và bên liên quan

Trong một sản phẩm, người trả tiền, người quyết định mua và người trực tiếp sử dụng có thể là những người khác nhau. Nhóm cần gọi đúng vai trò của từng bên để không thiết kế nghiên cứu hoặc kịch bản kiểm thử dựa trên một hình dung quá đơn giản.

| Vai trò | Ý nghĩa | Câu hỏi cần trả lời |
|---|---|---|
| Người dùng trực tiếp | Người thao tác với sản phẩm để hoàn thành công việc | Họ đang cố làm việc gì? Điều gì khiến thao tác khó hoặc dễ? |
| Người mua hoặc người phê duyệt | Người quyết định mua, gia hạn hoặc cấp ngân sách | Kết quả nào khiến họ thấy khoản đầu tư có giá trị? |
| Người quản trị | Người cấu hình, phân quyền, quản lý tài khoản hoặc dữ liệu | Họ cần kiểm soát và quan sát điều gì? |
| Người chịu ảnh hưởng | Người không trực tiếp thao tác nhưng chịu tác động từ kết quả | Sản phẩm ảnh hưởng thế nào đến công việc hoặc quyền lợi của họ? |
| Bên vận hành và hỗ trợ | Nhân sự triển khai, chăm sóc khách hàng hoặc xử lý sự cố | Họ cần thông tin và công cụ nào để hỗ trợ người dùng? |

Một người có thể đảm nhiệm nhiều vai trò. Ngược lại, một vai trò có thể gồm nhiều nhóm người với nhu cầu khác nhau. Hãy ghi nhận sự khác biệt có ảnh hưởng đến hành vi, quyền hạn, kỳ vọng hoặc rủi ro; không cần tạo một chân dung riêng cho mọi biến thể nhỏ.

### Phân khúc người dùng theo nhu cầu và bối cảnh

Phân khúc hữu ích giúp nhóm nhận ra những người có mục tiêu hoặc điều kiện sử dụng khác nhau. Có thể xem xét các chiều sau:

- **Mục tiêu và công việc:** người dùng muốn hoàn thành nhiệm vụ nào, kết quả cuối cùng là gì.
- **Tần suất và mức độ thành thạo:** họ dùng sản phẩm hằng ngày hay chỉ thỉnh thoảng; họ là người mới hay người có kinh nghiệm.
- **Bối cảnh sử dụng:** dùng tại văn phòng, ngoài hiện trường, trên thiết bị di động, trong môi trường mạng không ổn định hay trong điều kiện hạn chế thời gian.
- **Quyền hạn và trách nhiệm:** họ được xem, tạo, sửa, phê duyệt hoặc xóa dữ liệu nào; sai sót có thể ảnh hưởng đến ai.
- **Ràng buộc tiếp cận:** ngôn ngữ, khả năng tiếp cận, thiết bị, đường truyền và các yêu cầu hỗ trợ khác.

Không nên phân khúc chỉ theo tuổi, chức danh hoặc đặc điểm nhân khẩu học nếu những yếu tố đó không giải thích được hành vi hay nhu cầu liên quan đến sản phẩm.

### Mô tả nhu cầu bằng công việc người dùng muốn hoàn thành

Một cách diễn đạt hữu ích là cấu trúc:

> Khi [bối cảnh hoặc tác nhân kích hoạt], tôi muốn [việc cần hoàn thành], để [kết quả hoặc giá trị mong muốn].

Ví dụ: “Khi bắt đầu một dự án mới, trưởng nhóm muốn phân công công việc và theo dõi tiến độ ở cùng một nơi để cả nhóm biết việc tiếp theo cần làm.” Câu này mô tả bối cảnh, nhu cầu và kết quả. Nó không áp đặt trước giải pháp như “cần một màn hình có năm nút”.

Với mỗi nhóm người dùng chính, hãy ghi lại:

1. Mục tiêu quan trọng nhất và lý do mục tiêu đó quan trọng.
2. Tác nhân kích hoạt nhu cầu.
3. Cách họ đang giải quyết vấn đề, kể cả giải pháp thủ công hoặc công cụ thay thế.
4. Trở ngại, rủi ro và điều kiện khiến họ không thể hoàn thành công việc.
5. Dấu hiệu cho thấy họ đã đạt được kết quả mong muốn.

Đây là cơ sở để viết giả thuyết có thể kiểm chứng. Ví dụ: “Người quản trị có thể mời đồng nghiệp và thiết lập quyền truy cập mà không cần nhờ bộ phận hỗ trợ” là một giả thuyết về khả năng tự phục vụ; nhóm có thể kiểm tra bằng quan sát tác vụ, tỷ lệ hoàn thành và số lần cần trợ giúp.

### Dựa vào bằng chứng thay vì giả định

Chân dung người dùng và nhu cầu phải được xây dựng từ dữ liệu có nguồn gốc rõ ràng. Các nguồn thường hữu ích gồm:

- Phỏng vấn người dùng và người mua để hiểu mục tiêu, quyết định và cách họ diễn giải vấn đề.
- Quan sát người dùng thực hiện công việc trong bối cảnh thực tế để phát hiện thao tác vòng, công cụ phụ và cách xử lý ngoại lệ.
- Phân tích dữ liệu sử dụng để tìm bước rời bỏ, thời gian hoàn thành, tần suất lỗi và khác biệt giữa các nhóm.
- Đọc phản hồi hỗ trợ, khiếu nại, yêu cầu tính năng và ghi chú từ đội bán hàng hoặc triển khai.
- Kiểm thử khả năng sử dụng nguyên mẫu để xem người dùng có hiểu đề xuất và hoàn thành tác vụ hay không.

Mỗi nguồn có giới hạn riêng. Phỏng vấn cho biết người dùng nghĩ và nhớ điều gì, nhưng không luôn phản ánh chính xác hành vi. Dữ liệu phân tích cho biết điều gì xảy ra, nhưng thường không giải thích đầy đủ nguyên nhân. Hãy kết hợp nhiều nguồn và ghi rõ đâu là quan sát, đâu là diễn giải, đâu là giả định cần kiểm tra.

## 2. Xác định mục tiêu kinh doanh và giá trị cần tạo ra

### Kết nối mục tiêu kinh doanh với giá trị người dùng

Mục tiêu kinh doanh mô tả kết quả tổ chức muốn đạt được, chẳng hạn tăng doanh thu định kỳ, giảm chi phí hỗ trợ, mở rộng nhóm khách hàng hoặc giảm rủi ro vận hành. Mục tiêu sản phẩm giải thích sản phẩm sẽ đóng góp vào kết quả đó bằng cách nào. Giá trị người dùng cho biết vì sao người dùng sẽ lựa chọn và tiếp tục sử dụng sản phẩm.

Ba lớp này cần liên kết với nhau. Ví dụ:

- Doanh nghiệp muốn tăng tỷ lệ khách hàng dùng thử chuyển sang trả phí.
- Sản phẩm cần giúp nhóm khách hàng mới nhận được giá trị trong thời gian ngắn hơn.
- Người dùng cần thiết lập không gian làm việc, mời đồng nghiệp và hoàn thành công việc đầu tiên dễ dàng.

Nếu chỉ đặt mục tiêu “tăng số lượt nhấp vào nút đăng ký”, nhóm có thể cải thiện lượt nhấp nhưng không cải thiện việc người dùng có nhận được giá trị hay không. Mục tiêu tốt cần diễn tả kết quả, đối tượng và khoảng thời gian hoặc phạm vi đo lường.

### Chuyển mục tiêu thành chỉ số có thể quan sát

Nên phân biệt chỉ số kết quả với chỉ số dẫn dắt:

- **Chỉ số kết quả** phản ánh mục tiêu cuối cùng, ví dụ tỷ lệ gia hạn, doanh thu định kỳ, tỷ lệ hoàn thành công việc hoặc chi phí hỗ trợ trên mỗi khách hàng.
- **Chỉ số dẫn dắt** phản ánh hành vi có thể góp phần tạo ra kết quả, ví dụ tỷ lệ thiết lập thành công, tỷ lệ mời được thành viên đầu tiên hoặc thời gian đến lần đầu tiên hoàn thành tác vụ.
- **Chỉ số bảo vệ** giúp phát hiện việc cải thiện một chỉ số đang gây tổn hại ở nơi khác, ví dụ tỷ lệ lỗi, yêu cầu hỗ trợ, hủy dịch vụ, vi phạm quyền truy cập hoặc thời gian phản hồi.

Khi chọn một chỉ số, cần định nghĩa rõ:

- Tử số và mẫu số được tính như thế nào.
- Nhóm người dùng, khách hàng hoặc giao dịch nào được đưa vào.
- Khoảng thời gian đo và thời điểm bắt đầu tính.
- Nguồn dữ liệu và cách xử lý sự kiện thiếu hoặc trùng.
- Mức cơ sở hiện tại và ngưỡng thay đổi được xem là có ý nghĩa.

Ví dụ, “tăng tỷ lệ kích hoạt” chưa đủ rõ. Nhóm cần thống nhất kích hoạt là hành vi nào, tính trên tất cả tài khoản đăng ký hay chỉ tài khoản đủ điều kiện, và đo trong bao lâu kể từ lúc đăng ký.

| Mục tiêu kinh doanh | Giá trị người dùng cần nhận | Chỉ số có thể theo dõi | Chỉ số bảo vệ |
|---|---|---|---|
| Tăng tỷ lệ dùng thử chuyển sang trả phí | Người dùng nhận ra giá trị của sản phẩm trước khi kết thúc dùng thử | Tỷ lệ hoàn thành tác vụ cốt lõi; tỷ lệ chuyển đổi theo nhóm khách hàng | Tỷ lệ hủy sớm; số yêu cầu hỗ trợ |
| Giảm chi phí hỗ trợ | Người dùng tự giải quyết được các tác vụ phổ biến | Tỷ lệ tự hoàn thành; số liên hệ hỗ trợ trên mỗi tài khoản | Tỷ lệ tác vụ thất bại; mức hài lòng |
| Tăng mức độ sử dụng thường xuyên | Người dùng có lý do rõ ràng để quay lại hoàn thành công việc | Tỷ lệ quay lại theo tuần; tỷ lệ hoàn thành tác vụ lặp lại | Thông báo bị tắt; tỷ lệ rời bỏ |

Các chỉ số trên là ví dụ. Mỗi sản phẩm cần chọn chỉ số phù hợp với mô hình kinh doanh, giai đoạn phát triển và hành vi thực tế. Không nên chọn quá nhiều chỉ số chính vì điều đó làm loãng quyết định. Hãy xác định một kết quả chính, một số chỉ số dẫn dắt và các chỉ số bảo vệ cần thiết.

### Viết mục tiêu thành giả thuyết có thể kiểm chứng

Một giả thuyết tốt nêu rõ nhóm người dùng, thay đổi hoặc giải pháp, kết quả kỳ vọng và bằng chứng dùng để đánh giá. Có thể dùng cấu trúc:

> Chúng tôi tin rằng [thay đổi hoặc giải pháp] sẽ giúp [nhóm người dùng] [hoàn thành nhu cầu], từ đó cải thiện [kết quả hoặc chỉ số]. Chúng tôi sẽ kiểm tra giả thuyết bằng [phương pháp và bằng chứng]; giả thuyết được ủng hộ khi [tiêu chí đánh giá].

Ví dụ: “Chúng tôi tin rằng hướng dẫn thiết lập theo từng bước sẽ giúp quản trị viên mới mời thành viên và tạo công việc đầu tiên mà không cần hỗ trợ, qua đó rút ngắn thời gian đến giá trị đầu tiên. Chúng tôi sẽ quan sát người dùng mới thực hiện tác vụ và theo dõi tỷ lệ hoàn thành, thời gian hoàn thành cùng số lần cần trợ giúp.”

Trước khi kiểm thử, hãy xác định điều gì sẽ khiến nhóm giữ nguyên, điều chỉnh hoặc bác bỏ giả thuyết. Nếu không có tiêu chí quyết định, kết quả dễ bị diễn giải theo mong muốn ban đầu.

## 3. Lập bản đồ hành trình và xác định hành trình quan trọng

### Hành trình là gì?

Hành trình người dùng mô tả chuỗi bước từ khi nhu cầu xuất hiện đến khi người dùng đạt kết quả, bao gồm các điểm chạm với sản phẩm, con người và hệ thống liên quan. Hành trình có thể bắt đầu trước khi người dùng mở ứng dụng và kết thúc sau khi họ hoàn thành thao tác trong ứng dụng.

Một luồng giao diện thường mô tả các bước bên trong một chức năng. Hành trình rộng hơn: nó bao gồm mục tiêu, bối cảnh, kỳ vọng, cảm xúc, điểm chạm, chuyển giao giữa các bên và cách xử lý khi có vấn đề. Vì thế, kiểm thử một luồng giao diện thành công chưa đủ để kết luận hành trình đã đáp ứng nhu cầu.

### Xác định điểm bắt đầu và kết thúc

Trước khi vẽ hành trình, hãy trả lời:

- Nhu cầu hoặc sự kiện nào khởi đầu hành trình?
- Ai khởi đầu và ai tham gia ở các bước tiếp theo?
- Người dùng xem kết quả nào là hoàn thành?
- Hành trình có điểm chạm ngoài sản phẩm hay phụ thuộc hệ thống bên thứ ba nào?
- Điều gì xảy ra sau khi hoàn thành: xác nhận, thông báo, thanh toán, hỗ trợ hay hành động tiếp theo?

Phạm vi quá hẹp có thể bỏ sót nguyên nhân thực sự của vấn đề. Phạm vi quá rộng khiến bản đồ khó dùng để ra quyết định. Chọn một mục tiêu cụ thể và theo dõi đủ xa để xác nhận người dùng thực sự đạt được mục tiêu đó.

### Ghi lại các bước, điểm chạm và trở ngại

Với từng bước, nên ghi tối thiểu:

| Thành phần | Nội dung cần mô tả |
|---|---|
| Giai đoạn | Bước lớn trong hành trình |
| Người thực hiện | Người dùng, quản trị viên, nhân viên hỗ trợ hoặc hệ thống |
| Mục tiêu tại bước đó | Người thực hiện muốn đạt điều gì |
| Hành động và điểm chạm | Thao tác trên ứng dụng, email, trang web, cuộc gọi hoặc quy trình nội bộ |
| Dữ liệu và trạng thái | Dữ liệu đầu vào, quyền truy cập, trạng thái trước và sau thao tác |
| Kết quả mong đợi | Điều kiện để chuyển sang bước tiếp theo |
| Trở ngại và rủi ro | Nhầm lẫn, lỗi, chờ đợi, mất dữ liệu, sai quyền hoặc phụ thuộc bên ngoài |
| Cơ hội cải thiện | Cách giảm công sức, tăng độ rõ ràng hoặc hỗ trợ phục hồi |

Hãy lập bản đồ cho cả đường đi thuận lợi và các nhánh có khả năng xảy ra. Những nhánh thường bị bỏ qua gồm dữ liệu không hợp lệ, người dùng thiếu quyền, email không đến, mạng bị gián đoạn, dịch vụ bên ngoài không phản hồi, thao tác bị gửi lặp và người dùng cần quay lại sau khi rời giữa chừng.

Đặc biệt, cần mô tả cách người dùng nhận biết sự cố và tiếp tục công việc. Một thông báo lỗi có thể đúng về mặt kỹ thuật nhưng vẫn khiến hành trình thất bại nếu không chỉ ra nguyên nhân hoặc bước khắc phục.

### Chọn hành trình quan trọng

Không phải mọi hành trình đều cần cùng mức đầu tư kiểm chứng. Hãy ưu tiên dựa trên các yếu tố:

1. **Giá trị kinh doanh:** hành trình có ảnh hưởng trực tiếp đến doanh thu, giữ chân khách hàng, chi phí hoặc mục tiêu chiến lược không?
2. **Tầm quan trọng với người dùng:** nếu thất bại, người dùng có mất khả năng hoàn thành công việc cốt lõi không?
3. **Tần suất và phạm vi:** hành trình xảy ra thường xuyên hay ảnh hưởng đến nhiều người dùng hoặc khách hàng?
4. **Mức độ hậu quả:** lỗi có gây mất dữ liệu, sai giao dịch, lộ thông tin, vi phạm quyền hoặc gián đoạn nghiêm trọng không?
5. **Độ bất định:** nhóm còn thiếu bằng chứng về nhu cầu, cách hiểu, khả năng sử dụng hoặc tính khả thi không?
6. **Phụ thuộc:** hành trình có liên quan đến nhiều hệ thống, nhóm vận hành hoặc bên thứ ba không?

Có thể chấm từng yếu tố theo thang điểm thống nhất để hỗ trợ thảo luận, nhưng điểm số chỉ là công cụ so sánh. Hành trình có rủi ro nghiêm trọng về bảo mật, quyền riêng tư, an toàn hoặc tuân thủ cần được xem xét ưu tiên ngay cả khi tần suất thấp.

Một danh sách ưu tiên tốt giải thích được vì sao hành trình được chọn, ai chịu ảnh hưởng và bằng chứng nào còn thiếu. Tránh xếp hạng chỉ theo số lượt truy cập: một hành trình ít xảy ra nhưng có hậu quả lớn vẫn có thể là trọng yếu.

## 4. Ví dụ: hành trình thiết lập một không gian làm việc SaaS

Giả sử nhóm đang xác thực một sản phẩm SaaS giúp các nhóm phối hợp công việc. Đây là ví dụ minh họa cách kết nối người dùng, mục tiêu kinh doanh và hành trình; các chỉ số và giả thuyết cần được điều chỉnh theo dữ liệu thực tế của sản phẩm.

### Người dùng và mục tiêu

| Nhóm | Nhu cầu chính | Kết quả kinh doanh liên quan |
|---|---|---|
| Quản trị viên nhóm | Thiết lập không gian làm việc, mời thành viên và phân quyền đúng | Tài khoản dùng thử được kích hoạt; giảm công sức triển khai |
| Thành viên nhóm | Hiểu việc cần làm và hoàn thành công việc đầu tiên | Nhóm sớm nhận được giá trị và có khả năng quay lại |
| Người mua hoặc quản lý | Biết nhóm có sử dụng hiệu quả và đáp ứng yêu cầu hay không | Tăng khả năng chuyển đổi và gia hạn |
| Bộ phận IT hoặc bảo mật | Kiểm soát truy cập và xử lý dữ liệu theo chính sách | Giảm rủi ro và hỗ trợ triển khai ở tổ chức |

### Hành trình trọng yếu

| Giai đoạn | Mục tiêu người dùng | Điểm cần xác thực |
|---|---|---|
| Tạo tài khoản và không gian làm việc | Bắt đầu sử dụng mà không bị mắc ở bước đăng ký | Người dùng hiểu thông tin cần cung cấp; lỗi nhập liệu có hướng dẫn sửa |
| Cấu hình ban đầu | Thiết lập nhóm và quyền phù hợp | Quyền mặc định dễ hiểu; người quản trị biết ai có thể xem hoặc sửa dữ liệu |
| Mời thành viên | Đưa đúng người vào không gian làm việc | Lời mời được gửi và nhận; trạng thái lời mời rõ ràng; có cách gửi lại |
| Tạo công việc đầu tiên | Chuyển từ thiết lập sang công việc thực tế | Thành viên hiểu cách tạo, giao và cập nhật công việc |
| Quay lại và phối hợp | Tiếp tục công việc cùng nhóm | Thông báo hữu ích; trạng thái được cập nhật nhất quán; người dùng tìm lại được việc cần làm |

Từ bản đồ này, nhóm có thể chọn một số giả thuyết:

- Quản trị viên mới có thể thiết lập quyền và mời thành viên mà không cần trợ giúp.
- Thành viên mới có thể hiểu và hoàn thành công việc đầu tiên sau khi nhận lời mời.
- Nhóm có thể quay lại sản phẩm để tiếp tục công việc mà không phải tạo lại dữ liệu hoặc tìm kiếm quá lâu.

Các bằng chứng có thể gồm quan sát tác vụ với người dùng đại diện, tỷ lệ lời mời được chấp nhận, tỷ lệ nhóm tạo công việc đầu tiên, thời gian đến giá trị đầu tiên, số lần cần hỗ trợ và tỷ lệ quay lại. Cần kiểm tra cả trường hợp lời mời hết hạn, người nhận đã có tài khoản, người dùng không đủ quyền và thành viên rời nhóm.

Ví dụ này cho thấy một hành trình có thể liên quan đến nhiều vai trò và nhiều chỉ số. Nếu chỉ kiểm thử nút “Gửi lời mời” phản hồi thành công, nhóm vẫn chưa biết người nhận có nhận được lời mời, có tham gia được hay có hoàn thành công việc hay không.

## 5. Chuyển bối cảnh sản phẩm thành chiến lược kiểm thử xác thực

Sau khi xác định người dùng, mục tiêu và hành trình, hãy nối chúng thành một chuỗi có thể truy vết:

**Nhóm người dùng → Nhu cầu → Mục tiêu kinh doanh → Hành trình → Giả thuyết → Bằng chứng → Quyết định.**

Mỗi giả thuyết nên gắn với một hành trình và một kết quả cụ thể. Từ đó, nhóm lựa chọn phương pháp phù hợp:

| Câu hỏi cần xác thực | Phương pháp phù hợp | Bằng chứng cần thu thập |
|---|---|---|
| Người dùng có vấn đề này không và vấn đề có đủ quan trọng không? | Phỏng vấn, quan sát công việc, phân tích yêu cầu hỗ trợ | Tình huống thực tế, tần suất, giải pháp hiện tại và hậu quả |
| Người dùng có hiểu đề xuất hoặc nguyên mẫu không? | Kiểm thử khái niệm, kiểm thử khả năng sử dụng | Cách diễn giải, điểm nhầm lẫn, mức độ hoàn thành tác vụ |
| Người dùng có hoàn thành hành trình bằng sản phẩm không? | Kiểm thử tác vụ đầu cuối, thử nghiệm thực địa | Tỷ lệ hoàn thành, thời gian, lỗi, bước cần trợ giúp |
| Thay đổi có cải thiện hành vi hoặc kết quả không? | Thử nghiệm có đối chứng khi phù hợp, phân tích nhóm người dùng | Chênh lệch chỉ số, độ bất định và chỉ số bảo vệ |
| Hành trình có đáng tin cậy trong điều kiện thực tế không? | Kiểm thử tích hợp, kiểm thử lỗi và phục hồi, kiểm thử quyền | Trạng thái hệ thống, tính nhất quán dữ liệu, khả năng tiếp tục sau lỗi |

Kiểm thử xác thực sản phẩm và kiểm thử kỹ thuật bổ trợ cho nhau. Nghiên cứu người dùng có thể cho thấy một giải pháp dễ hiểu nhưng hệ thống vẫn có thể lưu sai dữ liệu. Kiểm thử chức năng có thể chứng minh một nút hoạt động theo yêu cầu nhưng chưa chứng minh người dùng có thể hoàn thành công việc có ý nghĩa. Chiến lược cần kết hợp bằng chứng về giá trị, khả năng sử dụng và hành vi hệ thống tùy theo rủi ro của hành trình.

Khi thiết kế nghiên cứu hoặc kiểm thử, hãy chọn người tham gia phù hợp với nhóm người dùng đã xác định. Nêu rõ tiêu chí tuyển chọn, bối cảnh sử dụng, thiết bị, quyền hạn và mức độ kinh nghiệm. Nếu chỉ mời những người dùng thành thạo hoặc nội bộ, kết quả có thể không đại diện cho người dùng mới hay nhóm có điều kiện sử dụng khác.

Trước khi bắt đầu, thống nhất cách ghi nhận kết quả. Ví dụ: thế nào là hoàn thành thành công, khi nào được tính là cần trợ giúp, lỗi nghiêm trọng được phân loại ra sao và ai có quyền quyết định tiếp tục, điều chỉnh hay dừng giả thuyết. Điều này giúp nhóm diễn giải bằng chứng nhất quán.

## 6. Các sai lầm thường gặp

- **Đồng nhất người mua với người dùng:** nhu cầu và tiêu chí thành công của hai nhóm có thể khác nhau; hãy xác định riêng vai trò và ảnh hưởng của họ.
- **Dùng chân dung giả định làm sự thật:** mọi nhận định chưa có bằng chứng cần được đánh dấu là giả định và đưa vào kế hoạch kiểm chứng.
- **Chọn chỉ số dễ đo thay cho chỉ số có ý nghĩa:** lượt nhấp hoặc lượt đăng nhập không tự chứng minh người dùng đã nhận được giá trị.
- **Chỉ vẽ đường đi thuận lợi:** bỏ qua lỗi, quyền truy cập, chờ đợi và phục hồi sẽ làm đánh giá thấp rủi ro thực tế.
- **Chỉ kiểm thử từng màn hình:** một bước thành công không đảm bảo toàn bộ hành trình hoàn tất.
- **Bỏ qua chỉ số bảo vệ:** cải thiện chuyển đổi nhưng làm tăng lỗi, khiếu nại hoặc rủi ro dữ liệu có thể khiến kết quả kinh doanh xấu đi.
- **Không xác định tiêu chí quyết định trước:** nhóm dễ diễn giải kết quả mơ hồ theo kỳ vọng thay vì bằng chứng.

## 7. Đầu ra cần có trước khi lập kế hoạch kiểm thử

Một bản tóm tắt bối cảnh sản phẩm đủ dùng nên có các nội dung sau:

1. **Phạm vi sản phẩm:** vấn đề sản phẩm giải quyết, ranh giới phạm vi và các hệ thống hoặc bên liên quan quan trọng.
2. **Nhóm người dùng:** vai trò, nhu cầu, bối cảnh, mức độ ưu tiên và nguồn bằng chứng.
3. **Mục tiêu kinh doanh:** kết quả mong muốn, chỉ số chính, chỉ số dẫn dắt và chỉ số bảo vệ.
4. **Hành trình trọng yếu:** điểm bắt đầu, điểm kết thúc, các bước, điểm chạm, phụ thuộc, nhánh lỗi và cách phục hồi.
5. **Giả thuyết cần xác thực:** nhóm người dùng, nhu cầu, thay đổi, kết quả kỳ vọng và tiêu chí đánh giá.
6. **Khoảng trống bằng chứng:** điều đã biết, điều đang giả định và câu hỏi cần nghiên cứu thêm.
7. **Ưu tiên và lý do:** hành trình hoặc giả thuyết nào cần kiểm tra trước, dựa trên giá trị, tần suất, hậu quả và độ bất định.

Có thể rà soát bản tóm tắt bằng các câu hỏi sau:

- Nhóm có thể giải thích rõ ai là người dùng chính và họ muốn hoàn thành công việc gì không?
- Mục tiêu kinh doanh có liên hệ trực tiếp với giá trị người dùng không?
- Các chỉ số có định nghĩa và nguồn dữ liệu đủ rõ để đo không?
- Hành trình có bao gồm các điểm chạm ngoài giao diện và các nhánh lỗi quan trọng không?
- Nhóm đã chọn hành trình ưu tiên dựa trên tác động và rủi ro chưa?
- Mỗi giả thuyết có phương pháp thu thập bằng chứng và tiêu chí ra quyết định không?
- Những giả định chưa được kiểm chứng đã được ghi rõ chưa?

Khi các câu trả lời này đủ rõ, nhóm có thể chuyển sang thiết kế kế hoạch kiểm thử: xác định câu hỏi nghiên cứu, người tham gia, phương pháp, kịch bản, dữ liệu cần ghi nhận và tiêu chí quyết định. Bối cảnh sản phẩm cần được cập nhật khi có bằng chứng mới, khi nhóm người dùng thay đổi hoặc khi mục tiêu kinh doanh chuyển hướng. Đây là đầu vào sống của chiến lược xác thực, không phải tài liệu chỉ lập một lần rồi bỏ quên.

